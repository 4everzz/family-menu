"""冰箱表的数据访问。

约定同其他 repository：这一层只管查和存，不写业务规则，也不调用 commit。
事务边界由 Service 或接口层决定。

列表查询会顺手 join users 把"添加者昵称"取回来，
避免前端渲染每条食材时再发请求查是谁加的（也避免 N+1）。
"""

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fridge_item import FridgeItem
from app.models.user import User


class FridgeRepository:
    """冰箱表的查询与写入。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ==================== 读 ====================

    async def get_detail(self, item_id: int) -> tuple[FridgeItem, str] | None:
        """按主键查单条食材，同时带上添加者昵称。不存在返回 None。"""
        stmt = (
            select(FridgeItem, User.nickname)
            .join(User, User.id == FridgeItem.created_by)
            .where(FridgeItem.id == item_id)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        return (row[0], row[1]) if row is not None else None

    async def list_by_space(
        self,
        space_id: int,
        category: str | None = None,
        storage: str | None = None,
        keyword: str | None = None,
    ) -> list[tuple[FridgeItem, str]]:
        """列出某个家庭组的食材，可按分类、存放、关键词筛选。

        返回 [(食材, 添加者昵称), ...]，按 id 升序（添加先后顺序，稳定可预期）。
        筛选条件都是可选叠加，用 if 逐条拼 where。
        """
        stmt = (
            select(FridgeItem, User.nickname)
            .join(User, User.id == FridgeItem.created_by)
            .where(FridgeItem.space_id == space_id)
        )

        if category:
            stmt = stmt.where(FridgeItem.category == category)
        if storage:
            stmt = stmt.where(FridgeItem.storage == storage)
        if keyword:
            # 食材名和备注一起搜：家人常记得"那盒快过期的牛奶"，不一定记得写的什么名
            pattern = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    FridgeItem.name.ilike(pattern),
                    FridgeItem.note.ilike(pattern),
                )
            )

        stmt = stmt.order_by(FridgeItem.id)
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def count_expiring(self, space_id: int, before_date: date) -> int:
        """统计这个家庭组里"需要在意保质期"的食材数量。

        before_date 一般取"今天 + N 天"。统计条件是：
            expiry_date 不为空，且 expiry_date <= before_date
        —— 于是"已经过期"和"N 天内临期"的都会算进去，都是该处理的。
        这个值用来给列表页顶部的"临期 N 件"提示，和当前筛选条件无关。
        """
        stmt = (
            select(func.count(FridgeItem.id))
            .where(
                FridgeItem.space_id == space_id,
                FridgeItem.expiry_date.isnot(None),
                FridgeItem.expiry_date <= before_date,
            )
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    # ==================== 写 ====================

    async def create(
        self,
        *,
        space_id: int,
        name: str,
        quantity: float,
        unit: str | None,
        category: str | None,
        storage: str | None,
        expiry_date: date | None,
        note: str | None,
        created_by: int,
    ) -> FridgeItem:
        """新增食材。返回的对象已带数据库生成的自增 ID。"""
        item = FridgeItem(
            space_id=space_id,
            name=name,
            quantity=quantity,
            unit=unit,
            category=category,
            storage=storage,
            expiry_date=expiry_date,
            note=note,
            created_by=created_by,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def update(self, item: FridgeItem, values: dict) -> FridgeItem:
        """按传入的字段更新食材（只改 values 里出现的键）。

        末尾这次 refresh 和菜谱仓库是同一个坑的修法：
            updated_at 由数据库端生成时间，UPDATE 之后这一列会被标记过期，
            commit 时连接已归还连接池，再读就会 MissingGreenlet（接口 500）。
            在还持有连接时先刷新出来，后面随便读。
        """
        for field, value in values.items():
            setattr(item, field, value)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def delete(self, item: FridgeItem) -> None:
        """删除食材。"""
        await self.session.delete(item)
        await self.session.flush()
