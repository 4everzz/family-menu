"""家庭提醒（异常状态聚合）业务规则。

提醒不是新业务数据，而是把现有几张表里的"该注意的状态"实时算出来：
本版本只做冰箱相关的两类——
  1. 临期 / 过期：食材保质期落在"今天 ~ 今天+3 天"内算临期（已过期更紧急，标 danger）。
  2. 缺货：食材库存 quantity <= 0 算缺货。

为什么纯读、不建表？
  提醒是派生数据，每次进页面实时算成本最低、也永远最新；
  v1 不持久化"已忽略"，所以不需要任何新表或迁移（和后端已确认：第四点同意不做持久化）。
"""

from datetime import date, timedelta

from app.models.fridge_item import FridgeItem
from app.models.user import User
from app.repositories.fridge_repo import FridgeRepository
from app.schemas.alert import AlertResponse
from app.services.space_service import SpaceService

# 临期窗口：保质期落在"今天 ~ 今天+3 天"内（含已过期）算临期提醒。
# 和冰箱列表页顶部的"临期件数"（用 7 天窗口）是两码事——那里是为了让家人尽早留意，
# 这里是"提醒"功能的精准阈值，按用户拍板取 3 天。放成常量便于以后调整。
ALERT_EXPIRING_WITHIN_DAYS = 3


class AlertService:
    """家庭提醒服务（只读聚合）。"""

    def __init__(self, repo: FridgeRepository, space_service: SpaceService) -> None:
        self.repo = repo
        # 复用家庭组成员校验：提醒的可见范围和冰箱一致，都按"是不是这个家庭成员"决定
        self.space_service = space_service

    async def list_alerts(
        self,
        user: User,
        space_id: int,
        today: date | None = None,
    ) -> list[AlertResponse]:
        """列出当前家庭组需要提醒的事项（仅冰箱临期/过期 + 缺货）。

        权限：必须是该家庭成员（ensure_member），否则拿别人的 space_id 也能看到别人家的库存状态。
        返回按紧急程度排：danger（已过期/缺货）在前，warning（临期）在后。
        """
        await self.space_service.ensure_member(space_id, user.id)

        today = today or date.today()
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

        # danger 在前，warning 在后；同级保持原顺序（按 id）
        alerts.sort(key=lambda a: 0 if a.level == "danger" else 1)
        return alerts
