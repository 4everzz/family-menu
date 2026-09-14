"""家庭冰箱业务规则。

权限口径（用户拍板，和菜单一致）：
    **只有创建人能改冰箱**——食材的新增、修改、删除都归创建人。
    普通成员只能浏览（列表、详情、搜索、筛选）。
    创建人专属权力一共三项：改菜单、改冰箱、解散家庭组 / 移除成员。

为什么和菜单用同一套权限，而不是"谁都能改"？
    冰箱也是这个家共享的资料，谁都能改就意味着任何人都能清空、删掉别人记的库存，
    一次误操作代价不可逆。收成一个人管，责任清楚，误操作面也小。
    （用户提供选项时明确选了"仅创建人可改"，没有采用早期"所有成员可改"的假设。）

两条安全原则（和菜谱完全一致）：
    1. "是不是家庭成员""是不是创建人"必须由后端查库判断，统一走
       SpaceService.ensure_member / ensure_owner。前端藏按钮只是体验，不是防线。
    2. 食材 ID 是自增可猜的，每个写接口都要先确认这条食材属于这个家庭组，
       否则拿自己的 space_id 配别人的 item_id 就能改到别人家的库存（越权）。
"""

from datetime import date, timedelta

from app.core.exceptions import BusinessError, NotFoundError
from app.models.fridge_item import FridgeItem
from app.models.user import User
from app.repositories.fridge_repo import FridgeRepository
from app.services.space_service import SpaceService

# 临期窗口：保质期落在"今天 ~ 今天+7 天"内（含已过期）算"需要在意"。
# 放成常量而不是写死在 SQL 里，将来想调成 3 天或 14 天只改这里。
EXPIRING_WITHIN_DAYS = 7


class FridgeService:
    """家庭冰箱服务。"""

    def __init__(self, repo: FridgeRepository, space_service: SpaceService) -> None:
        self.repo = repo
        # 复用家庭组的成员 / 创建人校验：冰箱的可见范围和"能不能改"完全由它决定
        self.space_service = space_service

    # ==================== 读操作 ====================

    async def list_items(
        self,
        user: User,
        space_id: int,
        category: str | None = None,
        storage: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[tuple[FridgeItem, str]], int]:
        """列出某个家庭组的食材，可按分类、存放、关键词筛选。

        返回 (食材列表, 临期件数)。
        临期件数和当前筛选条件无关，始终统计整个家庭组的，这样顶部提示保持稳定。
        """
        await self.space_service.ensure_member(space_id, user.id)
        rows = await self.repo.list_by_space(space_id, category, storage, keyword)
        before_date = date.today() + timedelta(days=EXPIRING_WITHIN_DAYS)
        expiring_count = await self.repo.count_expiring(space_id, before_date)
        return rows, expiring_count

    async def get_item(self, user: User, space_id: int, item_id: int) -> tuple[FridgeItem, str]:
        """查看单条食材（返回食材、添加者昵称）。"""
        await self.space_service.ensure_member(space_id, user.id)
        return await self._get_owned_item(space_id, item_id)

    # ==================== 写操作 ====================

    async def create_item(
        self,
        user: User,
        space_id: int,
        *,
        name: str,
        quantity: float,
        unit: str | None,
        category: str | None,
        storage: str | None,
        expiry_date: date | None,
        note: str | None,
    ) -> FridgeItem:
        """新增食材（仅创建人）。"""
        await self.space_service.ensure_owner(space_id, user.id)
        return await self.repo.create(
            space_id=space_id,
            name=self._normalize_name(name),
            quantity=float(quantity),
            unit=self._normalize_optional_str(unit, 8, "单位"),
            category=self._normalize_optional_str(category, 16, "分类"),
            storage=self._normalize_optional_str(storage, 8, "存放"),
            expiry_date=expiry_date,
            note=self._normalize_optional_str(note, 200, "备注"),
            created_by=user.id,
        )

    async def update_item(
        self,
        user: User,
        space_id: int,
        item_id: int,
        changes: dict,
    ) -> FridgeItem:
        """部分更新食材（仅创建人）。

        changes 只包含请求体里真正出现过的字段（接口层用 exclude_unset 取出来），
        所以逐个 "if 键在不在" 地判断，没传的字段一律不碰。
        """
        await self.space_service.ensure_owner(space_id, user.id)
        item, _ = await self._get_owned_item(space_id, item_id)

        values: dict = {}
        if "name" in changes:
            values["name"] = self._normalize_name(changes["name"])
        if "quantity" in changes:
            # 数量已经过 Pydantic 校验（>0），这里转成 float 存，避免 Decimal
            values["quantity"] = float(changes["quantity"])
        if "unit" in changes:
            values["unit"] = self._normalize_optional_str(changes["unit"], 8, "单位")
        if "category" in changes:
            values["category"] = self._normalize_optional_str(changes["category"], 16, "分类")
        if "storage" in changes:
            values["storage"] = self._normalize_optional_str(changes["storage"], 8, "存放")
        if "expiry_date" in changes:
            # 显式传 null 表示"不关注保质期"，要能清空，所以不在这里做非空判断
            values["expiry_date"] = changes["expiry_date"]
        if "note" in changes:
            values["note"] = self._normalize_optional_str(changes["note"], 200, "备注")

        if not values:
            # 一个字段都没传（空请求体），原样返回，省一条无意义的 UPDATE
            return item

        return await self.repo.update(item, values)

    async def delete_item(self, user: User, space_id: int, item_id: int) -> None:
        """删除食材（仅创建人）。"""
        await self.space_service.ensure_owner(space_id, user.id)
        item, _ = await self._get_owned_item(space_id, item_id)
        await self.repo.delete(item)

    # ==================== 内部工具 ====================

    async def _get_owned_item(self, space_id: int, item_id: int) -> tuple[FridgeItem, str]:
        """取出食材，并确认它确实属于这个家庭组（防越权）。

        查不到和不属于这个家，对外统一说"食材不存在"（404），不区分两种情况——
        说得越细，越方便别人拿脚本试探哪些 ID 是真的。
        """
        row = await self.repo.get_detail(item_id)
        if row is None:
            raise NotFoundError("食材不存在")

        item, nickname = row
        if item.space_id != space_id:
            raise NotFoundError("食材不存在")

        return item, nickname

    @staticmethod
    def _normalize_name(value: str | None) -> str:
        """清洗食材名：去首尾空格，不接受空名字。"""
        cleaned = (value or "").strip()
        if not cleaned:
            raise BusinessError("食材名不能为空")
        return cleaned

    @staticmethod
    def _normalize_optional_str(value: str | None, max_len: int, label: str) -> str | None:
        """清洗可选字符串字段（单位/分类/存放/备注）。

        空字符串一律转成 None（"没填"），避免数据库里散落一堆空串。
        超过长度上限给一句人话，而不是让数据库抛违反长度约束的错误。
        """
        if value is None:
            return None
        cleaned = str(value).strip()
        if not cleaned:
            return None
        if len(cleaned) > max_len:
            raise BusinessError(f"{label}过长（最多 {max_len} 个字）")
        return cleaned
