"""家庭提醒（异常状态聚合）业务规则。

提醒不是新业务数据，而是把现有几张表里的"该注意的状态"实时算出来：
  1. 临期 / 过期：食材保质期落在"今天 ~ 今天+3 天"内算临期（已过期更紧急，标 danger）。
  2. 缺货：食材库存 quantity <= 0 算缺货。
  3. 今日未点单：今天这个家还没有任何点单（标 info，是提示不是警告）。

为什么纯读、不建表？
  提醒是派生数据，每次进页面实时算成本最低、也永远最新；
  v1 不持久化"已忽略"，所以不需要任何新表或迁移（和后端已确认：第四点同意不做持久化）。
"""

from datetime import date, datetime, timedelta

from app.models.fridge_item import FridgeItem
from app.models.user import User
from app.repositories.fridge_repo import FridgeRepository
from app.repositories.order_repo import OrderRepository
from app.schemas.alert import AlertResponse
from app.services.space_service import SpaceService

# 临期窗口：保质期落在"今天 ~ 今天+3 天"内（含已过期）算临期提醒。
# 和冰箱列表页顶部的"临期件数"（用 7 天窗口）是两码事——那里是为了让家人尽早留意，
# 这里是"提醒"功能的精准阈值，按用户拍板取 3 天。放成常量便于以后调整。
ALERT_EXPIRING_WITHIN_DAYS = 3

# 「今日未点单」从几点开始提示？
# 零点刚过就弹"今天还没点单"没有意义（没人会在凌晨点午饭），所以从上午 9 点起才提示。
# 想改成"全天提示"就设成 0；想更晚就调大。改这一个数即可，不用动别处。
ALERT_NO_ORDER_AFTER_HOUR = 9

# 排序优先级：数字越小越靠前。danger（已过期/缺货）最急，info（只是提示）垫底。
_LEVEL_RANK = {"danger": 0, "warning": 1, "info": 2}


class AlertService:
    """家庭提醒服务（只读聚合）。"""

    def __init__(
        self,
        repo: FridgeRepository,
        space_service: SpaceService,
        order_repo: OrderRepository,
    ) -> None:
        self.repo = repo
        self.order_repo = order_repo
        # 复用家庭组成员校验：提醒的可见范围和冰箱一致，都按"是不是这个家庭成员"决定
        self.space_service = space_service

    async def list_alerts(
        self,
        user: User,
        space_id: int,
        today: date | None = None,
        now: datetime | None = None,
    ) -> list[AlertResponse]:
        """列出当前家庭组需要提醒的事项（冰箱临期/过期 + 缺货 + 今日未点单）。

        权限：必须是该家庭成员（ensure_member），否则拿别人的 space_id 也能看到别人家的库存状态。
        返回按紧急程度排：danger（已过期/缺货）在前，warning（临期）次之，info（今日未点单）垫底。

        `today` / `now` 可注入，是为了让测试能固定"现在是哪天的几点"，
        不用去 mock 系统时钟；生产调用不传，走系统当前时间。
        """
        await self.space_service.ensure_member(space_id, user.id)

        now = now or datetime.now()
        today = today or now.date()
        threshold = today + timedelta(days=ALERT_EXPIRING_WITHIN_DAYS)

        rows = await self.repo.list_by_space(space_id)
        alerts: list[AlertResponse] = []

        for item, _nickname in rows:
            # ---- 临期 / 过期 ----
            if item.expiry_date is not None:
                if item.expiry_date < today:
                    level = "danger"
                    title = f"{item.name} 已过期"
                elif item.expiry_date <= threshold:
                    level = "warning"
                    days = (item.expiry_date - today).days
                    title = f"{item.name} {days} 天后过期"
                else:
                    level = None  # 还没到临期窗口，跳过

                if level is not None:
                    alerts.append(
                        AlertResponse(
                            id=f"fridge_expiring:{item.id}",
                            type="fridge_expiring",
                            level=level,
                            title=title,
                            detail=f"保质期 {item.expiry_date.isoformat()}",
                            related_id=item.id,
                            action=f"/pages/fridge/edit?id={item.id}",
                        )
                    )

            # ---- 缺货 ----
            if item.quantity <= 0:
                qty_text = f"{item.quantity:g}{item.unit or ''}"
                alerts.append(
                    AlertResponse(
                        id=f"fridge_out:{item.id}",
                        type="fridge_out",
                        level="danger",
                        title=f"{item.name} 缺货",
                        detail=f"库存 {qty_text}",
                        related_id=item.id,
                        action=f"/pages/fridge/edit?id={item.id}",
                    )
                )

        # ---- 今日未点单 ----
        # 只在"白天"提示：过了 ALERT_NO_ORDER_AFTER_HOUR 点、这个家今天还没有任何点单。
        # 级别用 info（最低档）——这是"提醒你去点菜"的提示，不是"食材坏了"那种警告，
        # 不该和过期/缺货抢注意力，所以排序垫底、配色也做得最轻。
        if now.hour >= ALERT_NO_ORDER_AFTER_HOUR and not await self.order_repo.has_orders_on(
            space_id, today
        ):
            alerts.append(
                AlertResponse(
                    id=f"order_empty_today:{space_id}:{today.isoformat()}",
                    type="order_empty_today",
                    level="info",
                    title="今天还没有人点单",
                    detail="把想吃的加进购物车提交，家人就能看到",
                    related_id=None,
                    # 纯信息条，不给跳转：菜单是 tabBar 页，navigateTo 到不了，
                    # 而 openAlert 的"仅创建人可点"也不适用于点单（点单是全员都能做的）。
                    action="",
                )
            )

        # 按紧急程度排：danger → warning → info；同级保持原顺序
        alerts.sort(key=lambda a: _LEVEL_RANK.get(a.level, 1))
        return alerts
