"""菜谱表的数据访问。

约定同其他 repository：这一层只管查和存，不写业务规则，也不调用 commit。
事务边界由 Service 或接口层决定。

这里所有查询都顺手 join 两次：
    一次 join users，把"添加者昵称"取回来；
    一次 join recipe_categories，把"分类名"取回来。
看起来多写了一点，但换来的是：前端渲染列表时不用为了显示"谁加的""属于哪一类"
再发请求，也不用自己维护一张"分类 id → 分类名"的映射表（那是很容易走偏的东西）。
同时也避免在循环里逐个菜谱去查关联表，也就是典型的 N+1 查询。
"""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recipe import Recipe
from app.models.recipe_category import RecipeCategory
from app.models.user import User


def _like_pattern(keyword: str) -> str:
    """把关键词包装成 LIKE 用的模糊匹配模式，并转义里面的特殊字符。

    LIKE 语法里 % 表示"任意多个字符"、_ 表示"任意一个字符"。
    用户如果搜 "糖醋_" 想找带下划线的菜名，不转义就会变成前缀匹配，结果莫名其妙。
    所以先把反斜杠本身、% 和 _ 这三个字符转义掉，让用户输入的内容按字面意思匹配。
    """
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class RecipeRepository:
    """菜谱表的查询与写入。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ==================== 读 ====================

    async def get_detail(self, recipe_id: int) -> tuple[Recipe, str, str] | None:
        """按主键查单条菜谱，同时带上添加者昵称和分类名。

        返回 (菜谱, 添加者昵称, 分类名)；不存在时返回 None。
        """
        stmt = (
            select(Recipe, User.nickname, RecipeCategory.name)
            .join(User, User.id == Recipe.created_by)
            .join(RecipeCategory, RecipeCategory.id == Recipe.category_id)
            .where(Recipe.id == recipe_id)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        return (row[0], row[1], row[2]) if row is not None else None

    async def list_by_space(
        self,
        space_id: int,
        category_id: int | None = None,
        keyword: str | None = None,
    ) -> list[tuple[Recipe, str, str]]:
        """列出某个家庭组的菜谱，可按分类和关键词筛选。

        返回 [(菜谱, 添加者昵称, 分类名), ...]，按 id 升序（也就是添加的先后顺序，
        稳定可预期；具体怎么分组、怎么排，交给前端按需处理）。

        注意筛选条件都是"可选叠加"，所以用 if 逐条拼 where——
        这样调用方想只看某个分类、或只想搜某个词，都不用另开一个接口。
        """
        stmt = (
            select(Recipe, User.nickname, RecipeCategory.name)
            .join(User, User.id == Recipe.created_by)
            .join(RecipeCategory, RecipeCategory.id == Recipe.category_id)
            .where(Recipe.space_id == space_id)
        )

        if category_id is not None:
            stmt = stmt.where(Recipe.category_id == category_id)

        if keyword:
            pattern = _like_pattern(keyword)
            # 菜名和做法一起搜：家人常常记得"里面放木耳的那道菜"，却不记得菜名
            stmt = stmt.where(
                or_(
                    Recipe.name.ilike(pattern, escape="\\"),
                    Recipe.description.ilike(pattern, escape="\\"),
                )
            )

        stmt = stmt.order_by(Recipe.id)
        result = await self.session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]

    # ==================== 写 ====================

    async def create(
        self,
        *,
        space_id: int,
        name: str,
        category_id: int,
        description: str | None,
        image_url: str | None,
        spice_options: list[str],
        default_spice: str | None,
        is_sold_out: bool,
        created_by: int,
    ) -> Recipe:
        """新增菜谱。返回的对象已带数据库生成的自增 ID。

        辣度相关三个字段是必填的（而不是给默认值）：
        它们该填什么由 Service 层算好——只认固定的四档、默认档必须落在支持列表里。
        这里如果各自给一份默认值，就等于在两处各写一套规则，早晚会不一致。
        """
        recipe = Recipe(
            space_id=space_id,
            name=name,
            category_id=category_id,
            description=description,
            image_url=image_url,
            spice_options=spice_options,
            default_spice=default_spice,
            is_sold_out=is_sold_out,
            created_by=created_by,
        )
        self.session.add(recipe)
        await self.session.flush()
        return recipe

    async def update(self, recipe: Recipe, values: dict) -> Recipe:
        """按传入的字段更新菜谱（只改 values 里出现的键）。

        末尾这次 refresh 不是多余的，它修的是一个异步环境下的坑：
            updated_at 的取值口径是"由数据库生成时间"（见 models/base.py 的说明），
            所以 UPDATE 之后这一列会被 SQLAlchemy 标记成过期，等到下次访问才去重新读。
            而接口层的顺序是"先 update、再 commit"，commit 时会话已经把连接还回连接池了。
            这时候再回头读 recipe.updated_at，就变成"在非异步上下文里发起数据库请求"，
            直接抛 MissingGreenlet（现象是接口 500，但代码看起来毫无问题，很难查）。
            所以在**还持有连接的时候**先把它刷出来，后面随便读都没事。
        """
        for field, value in values.items():
            setattr(recipe, field, value)
        await self.session.flush()
        await self.session.refresh(recipe)
        return recipe

    async def delete(self, recipe: Recipe) -> None:
        """删除菜谱。"""
        await self.session.delete(recipe)
        await self.session.flush()

    async def count_by_space(self, space_id: int) -> int:
        """统计某个家庭组的菜谱数量。"""
        stmt = select(func.count(Recipe.id)).where(Recipe.space_id == space_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())
