"""菜谱分类业务规则。

权限口径和菜谱模块完全一致：
    **只有创建人能改菜单**——新增、改名、删除分类都归创建人，普通成员只能浏览。
    校验统一走 SpaceService.ensure_owner，不在这里再写一遍"查成员表 + 比 owner_id"。

一条安全原则（和菜谱模块同一个道理）：
    分类 ID 是数据库自增的，很容易被猜到。
    所以凡是拿 category_id 做事的接口，都必须额外确认"这个分类确实属于这个家庭组"，
    否则拿自己的 space_id 配一个别人家的 category_id 就能操作别人家的数据。
    对外统一说"分类不存在"（404），不区分"真没有"和"不属于这个家"——
    说得越细，越方便别人拿脚本去试探哪些 ID 是真的。

删除分类为什么要拦？
    分类和菜谱是"一对多"的关系。如果允许直接删掉一个还有菜的分类，
    那些菜就失去了归属，既搜不到也显示不出来，等于凭空消失。
    所以规则是：**分类里还有菜就不让删**，提示用户先把菜移走。
    数据库那边同样设了 RESTRICT 作为兜底（见 models/recipe.py）。
"""

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import BusinessError, NotFoundError
from app.models.recipe_category import RecipeCategory
from app.models.user import User
from app.repositories.category_repo import CategoryRepository
from app.services.space_service import SpaceService


class CategoryService:
    """家庭菜谱分类服务。"""

    def __init__(self, repo: CategoryRepository, space_service: SpaceService) -> None:
        self.repo = repo
        # 复用家庭组的成员校验：分类的可见范围完全由"是不是这个家的人"决定
        self.space_service = space_service

    # ==================== 读操作 ====================

    async def list_categories(self, user: User, space_id: int) -> list[tuple[RecipeCategory, int]]:
        """列出某个家庭组的全部分类（带每类菜数）。"""
        await self.space_service.ensure_member(space_id, user.id)
        return await self.repo.list_by_space_with_count(space_id)

    async def count_recipes(self, category_id: int) -> int:
        """统计某个分类下的菜谱数量。

        给接口层在改名之后组装返回值用，让"修改分类"的返回结构和"分类列表"保持一致。

        这里刻意不再做一次成员校验：能走到这一步的调用方，
        都已经在自己那一步确认过"是家庭成员"且"这个分类属于这个家"。
        重复校验不会更安全，只是让每次改分类都多两次数据库查询。
        """
        return await self.repo.count_recipes(category_id)

    # ==================== 写操作 ====================

    async def create_category(self, user: User, space_id: int, name: str) -> RecipeCategory:
        """新增一个分类，排在最末尾（仅创建人）。"""
        await self.space_service.ensure_owner(space_id, user.id)
        cleaned = self._normalize_name(name)

        # 先查一次重名，目的是给出友好提示（"已经有一个叫「早餐」的分类了"）。
        # 这不是安全防线——并发时可能被插队，真正的拦截靠数据库的唯一约束。
        if await self.repo.get_by_name(space_id, cleaned) is not None:
            raise BusinessError(f"已经有一个叫「{cleaned}」的分类了")

        sort_order = await self.repo.max_sort_order(space_id) + 1
        try:
            category = await self.repo.create(space_id=space_id, name=cleaned, sort_order=sort_order)
        except IntegrityError as error:
            # 走到这里说明刚才那次查重和这次插入之间，别人插了一条同名的进来。
            # 事务已经因为这个错误作废了，必须先回滚，否则后面所有查询都会继续报错。
            await self.repo.session.rollback()
            raise BusinessError(f"已经有一个叫「{cleaned}」的分类了") from error

        return category

    async def rename_category(
        self,
        user: User,
        space_id: int,
        category_id: int,
        name: str,
    ) -> RecipeCategory:
        """给分类改名（仅创建人）。

        改名的成本很低——菜谱是通过 category_id 关联分类的，
        所以这里改一行，所有挂在这个分类下的菜自动跟着显示新名字，不用去动菜谱表。
        这正是当初选择"外键关联"而不是"在菜谱里存分类名"的原因。
        """
        await self.space_service.ensure_owner(space_id, user.id)
        category = await self.ensure_category_in_space(space_id, category_id)
        cleaned = self._normalize_name(name)

        if cleaned == category.name:
            # 名字没变就直接返回，省一条没有意义的 UPDATE。
            # 不报错——前端"点开改名又原样保存"是常见操作。
            return category

        existing = await self.repo.get_by_name(space_id, cleaned)
        if existing is not None and existing.id != category_id:
            raise BusinessError(f"已经有一个叫「{cleaned}」的分类了")

        try:
            return await self.repo.update(category, {"name": cleaned})
        except IntegrityError as error:
            await self.repo.session.rollback()
            raise BusinessError(f"已经有一个叫「{cleaned}」的分类了") from error

    async def delete_category(self, user: User, space_id: int, category_id: int) -> None:
        """删除分类（仅创建人）。分类下还有菜时拒绝删除。"""
        await self.space_service.ensure_owner(space_id, user.id)
        category = await self.ensure_category_in_space(space_id, category_id)

        recipe_count = await self.repo.count_recipes(category_id)
        if recipe_count > 0:
            raise BusinessError(
                f"「{category.name}」下还有 {recipe_count} 道菜，"
                "请先把它们改到别的分类，再删除这个分类"
            )

        try:
            await self.repo.delete(category)
        except IntegrityError as error:
            # 兜底：刚才那次计数和这次删除之间，别人往这个分类里加了菜。
            # 应用层的检查没拦住，但数据库的 RESTRICT 拦住了，数据没丢。
            await self.repo.session.rollback()
            raise BusinessError(f"「{category.name}」下还有菜谱，无法删除") from error

    # ==================== 供其他模块复用 ====================

    async def ensure_category_in_space(self, space_id: int, category_id: int) -> RecipeCategory:
        """确认这个分类确实属于这个家庭组，返回分类对象。

        这是给菜谱模块复用的：
        新增或修改菜谱时，必须确认用户选的那个分类是**本家的**分类，
        否则就能把菜挂到别人家的分类上——数据会错乱，而且跨家庭组还能互相看见。

        注意这个方法只校验"归属"，不校验"你是不是这个家的人"。
        调用方必须先自己 ensure_member，再调这个方法。
        两边分开是因为：能改菜的人未必在做和分类有关的操作，
        强行在这里再查一次成员表，等于每次改菜谱都多一次无用的数据库查询。
        """
        category = await self.repo.get_by_id(category_id)
        if category is None or category.space_id != space_id:
            raise NotFoundError("分类不存在")
        return category

    # ==================== 内部工具 ====================

    @staticmethod
    def _normalize_name(value: str | None) -> str:
        """清洗分类名：去掉首尾空格，不接受空名字。

        长度上限交给 Pydantic 的 max_length 管（超长直接 422），
        这里只管"看起来有内容、其实全是空格"这种 Pydantic 看不出来的情况。
        """
        cleaned = (value or "").strip()
        if not cleaned:
            raise BusinessError("分类名不能为空")
        return cleaned
