"""收藏相关的数据访问。

约定同其它 repository：只管查和存，不写业务规则，也不调用 commit。

两个值得说明的设计：
1. **默认收藏夹在这里表现为 None**。
   它不是一行数据，所以"查默认收藏夹里的收藏"就是查 partition_id IS NULL。
   所有涉及分区的查询都要考虑 NULL 这个分支——漏了它，默认栏就会显示为空。
2. 统计和列表都尽量一次查完（GROUP BY / JOIN），不在 Service 里循环查库，
   避免分区一多就变成 N+1 查询。
"""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.favorite import FavoritePartition, RecipeFavorite
from app.models.recipe import Recipe
from app.models.recipe_category import RecipeCategory
from app.models.space import Space


class FavoriteRepository:
    """收藏分区与收藏记录的查询与写入。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ==================== 分区 ====================

    async def list_partitions(self, user_id: int) -> list[FavoritePartition]:
        """列出用户的全部分区，按 sort_order 升序（同序时按 id，保证稳定）。"""
        stmt = (
            select(FavoritePartition)
            .where(FavoritePartition.user_id == user_id)
            .order_by(FavoritePartition.sort_order, FavoritePartition.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_partition(self, user_id: int) -> dict[int | None, int]:
        """统计每个分区下有几条收藏。返回 {partition_id: 数量}，默认收藏夹的键是 None。

        一次 GROUP BY 查完所有分区的数量；
        若在 Service 里逐个分区查，6 个分区就是 7 次数据库往返。
        """
        stmt = (
            select(RecipeFavorite.partition_id, func.count(RecipeFavorite.id))
            .where(RecipeFavorite.user_id == user_id)
            .group_by(RecipeFavorite.partition_id)
        )
        result = await self.session.execute(stmt)
        return {partition_id: int(count) for partition_id, count in result.all()}

    async def get_partition(self, user_id: int, partition_id: int) -> FavoritePartition | None:
        """查某个分区。返回 None 可能是"不存在"也可能是"不是你的"——Service 统一按不存在处理。"""
        stmt = select(FavoritePartition).where(
            FavoritePartition.id == partition_id,
            FavoritePartition.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_partitions(self, user_id: int) -> int:
        """统计用户的自定义分区数量（额度校验用）。默认收藏夹不计入。"""
        stmt = (
            select(func.count(FavoritePartition.id))
            .where(FavoritePartition.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def max_sort_order(self, user_id: int) -> int:
        """当前最大的 sort_order，新建分区排在它后面。没有分区时返回 0。"""
        stmt = select(func.max(FavoritePartition.sort_order)).where(
            FavoritePartition.user_id == user_id
        )
        result = await self.session.execute(stmt)
        value = result.scalar_one()
        return int(value) if value is not None else 0

    async def add_partition(self, user_id: int, name: str, sort_order: int) -> FavoritePartition:
        """新建分区。"""
        partition = FavoritePartition(user_id=user_id, name=name, sort_order=sort_order)
        self.session.add(partition)
        await self.session.flush()
        return partition

    async def delete_partition(self, partition: FavoritePartition) -> None:
        """删除分区。里面的收藏由 Service 先挪回默认收藏夹。"""
        await self.session.delete(partition)
        await self.session.flush()

    async def move_favorites_to_default(self, user_id: int, partition_id: int) -> int:
        """把某分区里的全部收藏挪回默认收藏夹（partition_id 置 NULL）。返回挪动条数。

        用一条 UPDATE 而不是"查出来再逐条改"：
        收藏可能有几十条，逐条改既慢又会触发多次 ORM 事件。
        这里用的是 Core 级 update，不把行加载进内存，也就不涉及刷新问题。
        """
        stmt = (
            update(RecipeFavorite)
            .where(
                RecipeFavorite.user_id == user_id,
                RecipeFavorite.partition_id == partition_id,
            )
            .values(partition_id=None)
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    # ==================== 收藏 ====================

    async def get_favorite(self, user_id: int, recipe_id: int) -> RecipeFavorite | None:
        """查某用户对某道菜是否已收藏（收藏是 (user_id, recipe_id) 唯一的，最多一行）。"""
        stmt = select(RecipeFavorite).where(
            RecipeFavorite.user_id == user_id,
            RecipeFavorite.recipe_id == recipe_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_favorite(
        self, user_id: int, recipe_id: int, partition_id: int | None
    ) -> RecipeFavorite:
        """新增收藏。partition_id 传 None 即默认收藏夹。"""
        favorite = RecipeFavorite(
            user_id=user_id,
            recipe_id=recipe_id,
            partition_id=partition_id,
        )
        self.session.add(favorite)
        await self.session.flush()
        return favorite

    async def update_favorite_partition(
        self, favorite: RecipeFavorite, partition_id: int | None
    ) -> RecipeFavorite:
        """把已有收藏挪到另一个分区（或挪回默认收藏夹）。

        ⚠️ 改完必须立刻 refresh：数据库端的 onupdate=now() 会在 flush 之后
        触发一次过期加载，如果不趁连接还在时取回，异步场景会抛 MissingGreenlet
        ——这个项目里 PATCH 类接口 500 的根因（见 space_service.py 的说明）。
        """
        favorite.partition_id = partition_id
        await self.session.flush()
        await self.session.refresh(favorite)
        return favorite

    async def delete_favorite(self, favorite: RecipeFavorite) -> None:
        """删除一条收藏记录（取消收藏）。"""
        await self.session.delete(favorite)
        await self.session.flush()

    async def list_favorites(
        self, user_id: int, partition_id: int | None
    ) -> list[tuple[RecipeFavorite, Recipe, str, str | None]]:
        """列出某分区下的收藏，带上菜谱摘要和家庭组名，按收藏时间倒序。

        partition_id 传 None 表示默认收藏夹（IS NULL），而不是"全部"。
        一次 JOIN 把菜谱、家庭组、分类名都取回来，
        不在 Service 里逐条查（否则收藏 20 道菜就是 60 次查询）。
        """
        stmt = (
            select(RecipeFavorite, Recipe, Space.name, RecipeCategory.name)
            .join(Recipe, Recipe.id == RecipeFavorite.recipe_id)
            .join(Space, Space.id == Recipe.space_id)
            .outerjoin(RecipeCategory, RecipeCategory.id == Recipe.category_id)
            .where(RecipeFavorite.user_id == user_id)
        )
        if partition_id is None:
            stmt = stmt.where(RecipeFavorite.partition_id.is_(None))
        else:
            stmt = stmt.where(RecipeFavorite.partition_id == partition_id)
        stmt = stmt.order_by(RecipeFavorite.id.desc())

        result = await self.session.execute(stmt)
        return [(row[0], row[1], row[2], row[3]) for row in result.all()]

    async def list_favorited_recipe_ids(self, user_id: int, space_id: int) -> list[int]:
        """列出用户在某家庭组里已收藏的菜谱 ID（菜单页画星标用）。

        菜单页只需要"哪些菜是亮的"，不需要完整收藏信息，
        所以只返回 ID 列表，一次轻量查询。
        """
        stmt = (
            select(RecipeFavorite.recipe_id)
            .join(Recipe, Recipe.id == RecipeFavorite.recipe_id)
            .where(
                RecipeFavorite.user_id == user_id,
                Recipe.space_id == space_id,
            )
        )
        result = await self.session.execute(stmt)
        return [int(row[0]) for row in result.all()]

    # ==================== 菜谱（只读，用于校验） ====================

    async def get_recipe(self, recipe_id: int) -> Recipe | None:
        """按 ID 查菜谱。收藏前要用它确认"这道菜存在、且你能看到它"。"""
        return await self.session.get(Recipe, recipe_id)
