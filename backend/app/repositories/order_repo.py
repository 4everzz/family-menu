"""点单表的数据访问。

与其它仓储同一套约定：只 flush、不 commit，事务边界交给接口层。
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dish_order import DishOrder, DishOrderItem
from app.models.recipe import Recipe
from app.models.user import User


class OrderRepository:
    """点单表的查询与写入。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_order(self, order_id: int) -> DishOrder | None:
        """按主键取一张点单。session.get 优先走一级缓存，比手写 select 省一次查询。"""
        return await self.session.get(DishOrder, order_id)

    async def get_order_with_nickname(self, order_id: int) -> tuple[DishOrder, str] | None:
        """按主键取点单，顺带把**提交者**的昵称查出来。

        为什么不直接用 session.get 就够了？
            响应里要显示"这单是谁提交的"，而改单的人不一定是提交者
            （创建人可以管成员提交的单）。想当然拿当前登录者的昵称填进去就会显示错人。
        """
        result = await self.session.execute(
            select(DishOrder, User.nickname)
            .join(User, User.id == DishOrder.created_by)
            .where(DishOrder.id == order_id)
        )
        row = result.first()
        return (row[0], row[1]) if row is not None else None

    async def list_by_space(
        self,
        space_id: int,
        status: str | None = None,
    ) -> list[tuple[DishOrder, str]]:
        """列出某个家庭组的点单，返回 [(点单, 提交者昵称)]，新的排在前面。

        join users 是为了顺带把昵称取出来，省得列表页再逐个查提交者。
        """
        stmt = (
            select(DishOrder, User.nickname)
            .join(User, User.id == DishOrder.created_by)
            .where(DishOrder.space_id == space_id)
            .order_by(DishOrder.created_at.desc(), DishOrder.id.desc())
        )
        if status:
            stmt = stmt.where(DishOrder.status == status)

        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def has_orders_on(self, space_id: int, day: date) -> bool:
        """某个家庭组在 `day` 这一天有没有点单。给「今日未点单」提醒用。

        为什么用显式的时刻区间，而不是 cast(created_at as date) = :day？
            created_at 是 timestamptz（存的是绝对时刻）。显式的绝对时刻区间是无歧义比较；
            交给 SQL 自己 cast 会依赖会话的 TimeZone 设置，换台机器/换个连接结果就可能变，
            这种"在 A 机器上对、在 B 机器上错"的坑最难查。所以边界在 Python 侧按本地时区算好。
        """
        tz = datetime.now().astimezone().tzinfo
        start = datetime.combine(day, time.min, tzinfo=tz)
        end = start + timedelta(days=1)
        result = await self.session.execute(
            select(DishOrder.id)
            .where(
                DishOrder.space_id == space_id,
                DishOrder.created_at >= start,
                DishOrder.created_at < end,
            )
            .limit(1)  # 只关心"有没有"，取 1 行即可，不必 count
        )
        return result.first() is not None

    async def list_items_grouped(self, order_ids: list[int]) -> dict[int, list[DishOrderItem]]:
        """一次取出多张点单的明细，按 order_id 分组。

        为什么要"一次查完"而不是每张点单查一次？
            列表页一屏可能显示十几张单，逐张查就是典型的 N+1：
            1 次列表查询 + N 次明细查询。这里用一条 IN 查询全部拿到。
        """
        if not order_ids:
            return {}

        result = await self.session.execute(
            select(DishOrderItem)
            .where(DishOrderItem.order_id.in_(order_ids))
            .order_by(DishOrderItem.id)
        )

        grouped: dict[int, list[DishOrderItem]] = {}
        for item in result.scalars().all():
            grouped.setdefault(item.order_id, []).append(item)
        return grouped

    async def get_recipes_in_space(
        self,
        space_id: int,
        recipe_ids: list[int],
    ) -> dict[int, Recipe]:
        """取出属于这个家庭组的菜谱，返回 {菜谱 ID: 菜谱}。

        ⚠️ 两个条件必须一起用：既要存在，又必须属于这个家庭组。
           否则拿自己的 space_id 配别人家的 recipe_id，
           就能把别人家的菜点进自己家的单子里（越权读）。
        """
        if not recipe_ids:
            return {}

        result = await self.session.execute(
            select(Recipe).where(Recipe.space_id == space_id, Recipe.id.in_(recipe_ids))
        )
        return {recipe.id: recipe for recipe in result.scalars().all()}

    async def create_order(
        self,
        *,
        space_id: int,
        created_by: int,
        guest_name: str | None,
        remark: str | None,
        status: str,
        items: list[tuple[int | None, str, str | None, int]],
    ) -> DishOrder:
        """新建点单及其明细。items 是 (菜谱 ID 或 None, 菜名快照, 辣度, 份数) 的列表。

        明细必须在拿到点单 ID 之后再插，所以中间要有一次 flush。
        """
        order = DishOrder(
            space_id=space_id,
            created_by=created_by,
            guest_name=guest_name,
            remark=remark,
            status=status,
        )
        self.session.add(order)
        await self.session.flush()  # 拿到数据库生成的点单 ID

        for recipe_id, dish_name, spice, quantity in items:
            self.session.add(
                DishOrderItem(
                    order_id=order.id,
                    recipe_id=recipe_id,
                    dish_name=dish_name,
                    spice=spice,
                    quantity=quantity,
                )
            )
        await self.session.flush()
        return order

    async def save(self, order: DishOrder) -> DishOrder:
        """把对象上已修改的字段写回数据库（只 flush，事务由上层提交）。"""
        self.session.add(order)
        await self.session.flush()
        return order

    async def delete_order(self, order: DishOrder) -> None:
        """删除点单。明细靠外键的 ON DELETE CASCADE 一起清掉。"""
        await self.session.delete(order)
        await self.session.flush()
