"""菜谱分类表的数据访问。

约定同其他 repository：这一层只管查和存，不写业务规则，也不调用 commit。
事务边界由 Service 或接口层决定。

分类和菜谱是强关联的两张表（分类被删时菜谱会跟着受影响），
所以这里的查询经常需要同时碰这两张表——比如"列出分类并带上每类的菜数"。
把这类查询写在这里，而不是在 Service 里循环调用，是为了避免 N+1 查询。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recipe import Recipe
from app.models.recipe_category import DEFAULT_CATEGORY_NAMES, RecipeCategory


class CategoryRepository:
    """分类表的查询与写入。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ==================== 读 ====================

    async def list_by_space_with_count(self, space_id: int) -> list[tuple[RecipeCategory, int]]:
        """列出某个家庭组的全部分类，并带上每个分类下的菜谱数量。

        返回 [(分类, 菜数), ...]，按 sort_order 升序（数字小的在前，也就是侧边栏顺序）。

        两个细节值得留意：
        1. 用 OUTER JOIN 而不是 INNER JOIN——刚建好的分类下面一道菜都没有，
           INNER JOIN 会让它直接消失，用户会以为"我新建的分类没保存上"。
        2. 一次查完所有分类的数量，而不是先查分类、再逐个查数量。
           后者是典型的 N+1 查询：6 个分类就是 7 次数据库往返，分类多起来更慢。
        """
        stmt = (
            select(RecipeCategory, func.count(Recipe.id))
            .outerjoin(Recipe, Recipe.category_id == RecipeCategory.id)
            .where(RecipeCategory.space_id == space_id)
            # 只按主键分组就够了：PostgreSQL 知道主键能唯一确定一行，
            # 所以同行的其他列不需要出现在 GROUP BY 里（函数依赖）。
            .group_by(RecipeCategory.id)
            .order_by(RecipeCategory.sort_order, RecipeCategory.id)
        )
        result = await self.session.execute(stmt)
        return [(row[0], int(row[1])) for row in result.all()]

    async def get_by_id(self, category_id: int) -> RecipeCategory | None:
        """按主键查分类，不存在返回 None。"""
        return await self.session.get(RecipeCategory, category_id)

    async def get_by_name(self, space_id: int, name: str) -> RecipeCategory | None:
        """按名字查分类，用来在新增/改名时提前给出"已经有同名分类"的友好提示。

        注意这只是体验优化，不是安全防线：
        真正的重名拦截是数据库上的唯一约束，因为并发情况下
        "先查有没有、再插入"这两步之间，别人可能刚好插了一条同名的进来。
        """
        stmt = select(RecipeCategory).where(
            RecipeCategory.space_id == space_id,
            RecipeCategory.name == name,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_recipes(self, category_id: int) -> int:
        """统计某个分类下有多少道菜。删除分类前用它判断能不能删。"""
        stmt = select(func.count(Recipe.id)).where(Recipe.category_id == category_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def max_sort_order(self, space_id: int) -> int:
        """取当前最大的排序值。新增分类时排在它后面。

        没有任何分类时返回 -1，这样"最大值 + 1"正好从 0 开始，不用特判。
        """
        stmt = select(func.max(RecipeCategory.sort_order)).where(RecipeCategory.space_id == space_id)
        result = await self.session.execute(stmt)
        value = result.scalar_one()
        return int(value) if value is not None else -1

    # ==================== 写 ====================

    async def create_defaults(self, space_id: int) -> list[RecipeCategory]:
        """给新家庭组批量插入默认分类。

        一次 add_all 只发一条 INSERT（SQLAlchemy 会合并成多值 VALUES），
        比循环单条插入快得多，而且在同一个事务里，不会出现"只插了一半"的状态。
        """
        categories = [
            RecipeCategory(space_id=space_id, name=name, sort_order=index)
            for index, name in enumerate(DEFAULT_CATEGORY_NAMES)
        ]
        self.session.add_all(categories)
        await self.session.flush()
        return categories

    async def create(self, *, space_id: int, name: str, sort_order: int) -> RecipeCategory:
        """新增一个分类。"""
        category = RecipeCategory(space_id=space_id, name=name, sort_order=sort_order)
        self.session.add(category)
        await self.session.flush()
        return category

    async def update(self, category: RecipeCategory, values: dict) -> RecipeCategory:
        """按传入的字段更新分类（目前只会用到 name 一个字段）。

        末尾这次 refresh 和菜谱那边同理，是为了绕开异步环境下的一个坑：
        updated_at 由数据库生成，UPDATE 之后这一列被标记为过期，
        而接口层紧接着 commit、会把连接还回连接池，
        这时候再读它就变成"在非异步上下文里发 SQL"，直接抛 MissingGreenlet。
        所以在还持有连接的时候先刷出来。
        """
        for field, value in values.items():
            setattr(category, field, value)
        await self.session.flush()
        await self.session.refresh(category)
        return category

    async def delete(self, category: RecipeCategory) -> None:
        """删除分类。

        如果这个分类下还有菜，数据库上的外键（RESTRICT）会直接拒绝这次删除，
        抛 IntegrityError。这是刻意留的兜底——应用层删之前会先查一次数量并给出友好提示，
        但"先查再删"之间存在时间差，RESTRICT 保证不会因此丢数据。
        """
        await self.session.delete(category)
        await self.session.flush()
