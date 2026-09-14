"""家庭菜谱业务规则。

权限口径（用户定的规则）：
    **只有创建人能改菜单**——新增、修改、删除菜谱，以及分类的增删改，都归创建人。
    普通成员只能浏览（列表、详情、搜索、筛选）。
    创建人专属权力一共三项：改菜单、解散家庭组、移除成员。

为什么是"创建人专属"而不是"谁都能改"？
    这是个产品决策，不是技术决策。理由很实在：菜谱是这个家共享的资料，
    谁都能改就意味着任何人都能改名、清空、删掉别人记的菜——一次误操作代价不可逆。
    收成一个人管，责任清楚，误操作面也小。
    （早期版本曾经放开给所有成员，后来按用户的要求收紧了。）

为什么不做"只能改自己加的"？
    那需要给创建人开例外分支，前端也得做一模一样的判断（按钮该不该显示），
    前后端两处规则只要有一点不一致，用户就会遇到"点了保存才被拒绝"这种最难查的问题。
    创建人一个角色判断就够了。

两条安全原则：
    1. "是不是这个家庭组的成员""是不是创建人"必须由后端查数据库判断，
       统一走 SpaceService.ensure_member / ensure_owner。
       前端把按钮藏起来只是体验优化，别人完全可以绕开界面直接调接口。
    2. 用户选的分类必须**属于这个家庭组**（由 CategoryService 校验）。
       分类 ID 是自增的、可猜的，不校验归属就能把菜挂到别人家的分类上，
       数据会错乱，而且跨家庭组还能互相看见。
"""

from app.core.exceptions import BusinessError, NotFoundError
from app.models.recipe import Recipe
from app.models.recipe_category import RecipeCategory
from app.models.user import User
from app.repositories.recipe_repo import RecipeRepository
from app.services.category_service import CategoryService
from app.services.space_service import SpaceService


class RecipeService:
    """家庭菜谱服务。"""

    def __init__(
        self,
        repo: RecipeRepository,
        space_service: SpaceService,
        category_service: CategoryService,
    ) -> None:
        self.repo = repo
        # 复用家庭组的成员校验：菜谱的可见范围完全由"是不是这个家的人"决定
        self.space_service = space_service
        # 复用分类的归属校验：确保菜不会挂到别人家的分类上
        self.category_service = category_service

    # ==================== 读操作 ====================

    async def list_recipes(
        self,
        user: User,
        space_id: int,
        category_id: int | None = None,
        keyword: str | None = None,
    ) -> list[tuple[Recipe, str, str]]:
        """列出某个家庭组的菜谱，可按分类和关键词筛选。

        分类是筛选条件而不是必填项，所以这里允许为空——没传就是不筛。

        筛选用的 category_id 不额外校验归属：
        因为查询本身还带着"必须是这个家庭组"的条件，
        就算传了别人家的分类 ID，结果也只会是空列表，读不到别人的数据。
        为这种情况多查一次数据库，换不来任何安全性。
        """
        await self.space_service.ensure_member(space_id, user.id)
        cleaned_keyword = (keyword or "").strip() or None
        return await self.repo.list_by_space(space_id, category_id, cleaned_keyword)

    async def get_recipe(self, user: User, space_id: int, recipe_id: int) -> tuple[Recipe, str, str]:
        """查看单条菜谱（返回菜谱、添加者昵称、分类名）。"""
        await self.space_service.ensure_member(space_id, user.id)
        return await self._get_owned_recipe(space_id, recipe_id)

    async def list_categories(self, user: User, space_id: int) -> list[tuple[RecipeCategory, int]]:
        """列出本家的分类（转交给 CategoryService）。

        菜单页一次渲染要拿两份数据：分类清单（侧边栏）+ 菜谱列表。
        这里做一层转发，让接口层只依赖 RecipeService 一个入口，
        而不用自己再组装一套 CategoryService——接口层越薄，
        越不容易出现"这个接口记得鉴权、那个接口忘了"的情况。
        """
        return await self.category_service.list_categories(user, space_id)

    # ==================== 写操作 ====================

    async def create_recipe(
        self,
        user: User,
        space_id: int,
        *,
        name: str,
        category_id: int,
        description: str | None,
        image_url: str | None,
    ) -> tuple[Recipe, str, str]:
        """新增菜谱（仅创建人）。返回 (菜谱, 添加者昵称, 分类名)。

        昵称直接用手上这个用户，不用再查库；分类名从校验那一步顺手拿到。
        """
        await self.space_service.ensure_owner(space_id, user.id)
        category = await self.category_service.ensure_category_in_space(
            space_id, self._normalize_category_id(category_id)
        )

        recipe = await self.repo.create(
            space_id=space_id,
            name=self._normalize_name(name),
            category_id=category.id,
            description=self._normalize_description(description),
            image_url=self._normalize_image_url(image_url),
            created_by=user.id,
        )
        return recipe, user.nickname, category.name

    async def update_recipe(
        self,
        user: User,
        space_id: int,
        recipe_id: int,
        changes: dict,
    ) -> tuple[Recipe, str, str]:
        """部分更新菜谱（仅创建人）。

        changes 只包含请求体里真正出现过的字段（接口层用 exclude_unset 取出来），
        所以这里逐个 "if 键在不在" 地判断，没传的字段一律不碰。
        """
        await self.space_service.ensure_owner(space_id, user.id)
        recipe, nickname, category_name = await self._get_owned_recipe(space_id, recipe_id)

        values: dict = {}
        if "name" in changes:
            values["name"] = self._normalize_name(changes["name"])
        if "category_id" in changes:
            # 换分类也要校验新分类属于本家，否则等于给"把菜挪到别人家分类下"开了口子
            category = await self.category_service.ensure_category_in_space(
                space_id, self._normalize_category_id(changes["category_id"])
            )
            values["category_id"] = category.id
            # 返回值里的分类名要跟着更新，不能还用旧的
            category_name = category.name
        if "description" in changes:
            values["description"] = self._normalize_description(changes["description"])
        if "image_url" in changes:
            values["image_url"] = self._normalize_image_url(changes["image_url"])

        if not values:
            # 一个字段都没传（空请求体），直接原样返回。
            # 不在这里报错：前端"打开编辑页又直接保存"是常见操作，没必要判成失败。
            # 顺便也省掉一条没有意义的 UPDATE。
            return recipe, nickname, category_name

        await self.repo.update(recipe, values)
        return recipe, nickname, category_name

    async def delete_recipe(self, user: User, space_id: int, recipe_id: int) -> None:
        """删除菜谱（仅创建人）。"""
        await self.space_service.ensure_owner(space_id, user.id)
        recipe, _, _ = await self._get_owned_recipe(space_id, recipe_id)
        await self.repo.delete(recipe)

    # ==================== 内部工具 ====================

    async def _get_owned_recipe(self, space_id: int, recipe_id: int) -> tuple[Recipe, str, str]:
        """取出菜谱，并确认它确实属于这个家庭组。

        这一步不能省：菜谱 ID 是自增的，很容易被猜到。
        如果不校验归属，只要拿自己的 space_id 配一个别人的 recipe_id，
        就能读到别人家的菜谱——这就是越权漏洞。

        查不到和不属于这个家，对外都统一说"菜谱不存在"（404），
        不区分两种情况——说得越细，越方便别人拿脚本去试探哪些 ID 是真的。
        """
        row = await self.repo.get_detail(recipe_id)
        if row is None:
            raise NotFoundError("菜谱不存在")

        recipe, nickname, category_name = row
        if recipe.space_id != space_id:
            raise NotFoundError("菜谱不存在")

        return recipe, nickname, category_name

    @staticmethod
    def _normalize_name(value: str | None) -> str:
        """清洗菜名：去掉首尾空格，不接受空名字。

        长度上限交给 Pydantic 的 max_length 管（超长直接 422），
        这里只管"看起来有内容、其实全是空格"这种 Pydantic 看不出来的情况。
        """
        cleaned = (value or "").strip()
        if not cleaned:
            raise BusinessError("菜名不能为空")
        return cleaned

    @staticmethod
    def _normalize_category_id(value: int | None) -> int:
        """校验分类 ID 是个合法的正整数。

        请求体里显式传 category_id: null 是"语法上合法但语义上不成立"的情况——
        一道菜必须挂在某个分类下（数据库那列也是 NOT NULL）。
        与其让数据库抛一个违反非空约束的错误（用户看不懂），
        不如在这里给一句人话。

        注意要特意排除 bool：Python 里 True 是 int 的子类，
        不排除的话 category_id=true 会被当成 1 悄悄放过去。
        """
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise BusinessError("请选择分类")
        return value

    @staticmethod
    def _normalize_description(value: str | None) -> str | None:
        """清洗做法文本。

        空字符串一律转成 None（"没填"），避免数据库里散落一堆空串——
        空串和 NULL 混着存，将来判"有没有做法"就得写两种条件，很容易漏。
        """
        if value is None:
            return None
        return value.strip() or None

    @staticmethod
    def _normalize_image_url(value: str | None) -> str | None:
        """清洗图片地址，空字符串按"没有图片"处理。"""
        return (value or "").strip() or None
