"""家庭菜谱接口。

接口层保持"薄"：只做三件事——收参数、调 Service、返回结果。
规则和校验都在 Service 层，这样同一个规则不会因为多个接口各写一遍而出现不一致。
"""

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.response import success
from app.models.recipe import Recipe
from app.repositories.category_repo import CategoryRepository
from app.repositories.recipe_repo import RecipeRepository
from app.repositories.space_repo import SpaceRepository
from app.schemas.category import CategoryInfo
from app.schemas.recipe import RecipeCreateRequest, RecipeInfo, RecipeUpdateRequest
from app.services.category_service import CategoryService
from app.services.recipe_service import RecipeService
from app.services.space_service import SpaceService

router = APIRouter(tags=["家庭菜谱"])


def _build_service(session: AsyncSession) -> RecipeService:
    """组装菜谱服务。

    菜谱的可见范围由"是不是这个家的人"决定，用户选的分类又必须属于这个家，
    所以这里把 SpaceService 和 CategoryService 都注入进去，
    而不是在菜谱服务里再写一遍"查成员表""查分类归属"的逻辑——鉴权只有一份实现，才不会漏。

    三个 Repository 共用同一个 session，所以它们处在同一个事务里，
    commit 一次就能把多边的写操作一起提交。
    """
    category_repo = CategoryRepository(session)
    space_service = SpaceService(SpaceRepository(session), category_repo)
    category_service = CategoryService(category_repo, space_service)
    return RecipeService(RecipeRepository(session), space_service, category_service)


def _to_recipe_info(recipe: Recipe, nickname: str | None, category_name: str) -> RecipeInfo:
    """把数据库对象组装成前端要的结构。

    字段是逐个列出来的，没有用 model_validate(recipe) 一把梭：
    category_name 和 created_by_nickname 是 join 出来的额外列、模型上并没有，
    混在一起写反而看不清哪些来自菜谱自身、哪些是拼进来的。
    代价是**加字段时要记得在这里补一行**——漏了不会报错，只会安静地少一个字段
    （辣度那次就是这么被测试抓出来的）。
    """
    return RecipeInfo(
        id=recipe.id,
        space_id=recipe.space_id,
        name=recipe.name,
        category_id=recipe.category_id,
        category_name=category_name,
        description=recipe.description,
        image_url=recipe.image_url,
        # JSON 列理论上可能是 NULL（老数据的 server_default 已兜住，这里再兜一层）
        spice_options=recipe.spice_options or [],
        default_spice=recipe.default_spice,
        is_sold_out=recipe.is_sold_out,
        created_by=recipe.created_by,
        created_by_nickname=nickname,
        created_at=recipe.created_at,
        updated_at=recipe.updated_at,
    )


@router.get("/spaces/{space_id}/recipes", summary="家庭菜谱列表")
async def list_recipes(
    space_id: int,
    current_user: CurrentUser,
    session: DbSession,
    category_id: int | None = Query(default=None, description="按分类筛选，不传表示全部"),
    keyword: str | None = Query(default=None, max_length=64, description="按菜名或做法模糊搜索"),
) -> dict:
    """列出当前家庭组的菜谱，同时带上分类清单。

    返回值刻意是个对象、而不是裸数组，因为要多带一个 categories：
    分类的先后顺序由后端定义，前端侧边栏直接照用。
    如果让前端自己抄一份分类清单，两边各存一份迟早会走偏——
    改了后端忘了改前端，用户就会看到"这儿有分类但永远点不出菜"。

    把两份数据放在同一个接口返回，是因为菜单页一次渲染就需要它们两个。
    分成两个请求的话，页面会出现"分类栏已经出来了、菜谱还在转圈"的错位感。
    """
    service = _build_service(session)
    rows = await service.list_recipes(current_user, space_id, category_id, keyword)
    category_rows = await service.list_categories(current_user, space_id)
    return success(
        {
            "categories": [
                CategoryInfo.from_model(category, count).model_dump()
                for category, count in category_rows
            ],
            "recipes": [
                _to_recipe_info(recipe, nickname, category_name).model_dump()
                for recipe, nickname, category_name in rows
            ],
        }
    )


@router.post("/spaces/{space_id}/recipes", summary="新增菜谱")
async def create_recipe(
    space_id: int,
    payload: RecipeCreateRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """在指定家庭组里新增一道菜。

    category_id 是必填的：一道菜必须挂在某个分类下。
    前端新增时的默认分类从分类列表接口的 is_default 字段拿，不要自己硬编码。
    """
    service = _build_service(session)
    recipe, nickname, category_name = await service.create_recipe(
        current_user,
        space_id,
        name=payload.name,
        category_id=payload.category_id,
        description=payload.description,
        image_url=payload.image_url,
        spice_options=payload.spice_options,
        default_spice=payload.default_spice,
        is_sold_out=payload.is_sold_out,
    )
    await session.commit()
    return success(_to_recipe_info(recipe, nickname, category_name).model_dump())


@router.get("/spaces/{space_id}/recipes/{recipe_id}", summary="菜谱详情")
async def get_recipe(
    space_id: int,
    recipe_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """查看单条菜谱。必须是该家庭成员，且这条菜确实属于这个家。"""
    service = _build_service(session)
    recipe, nickname, category_name = await service.get_recipe(current_user, space_id, recipe_id)
    return success(_to_recipe_info(recipe, nickname, category_name).model_dump())


# 同一个处理函数挂两个路由，原因是平台限制，不是设计冗余：
#   PATCH 是标准写法（部分更新语义最准确），留给将来打包成 App / H5 的客户端；
#   POST  是为了绕开微信小程序——wx.request 的 method 合法值只有
#         OPTIONS/GET/HEAD/POST/PUT/DELETE/TRACE/CONNECT，**没有 PATCH**，
#         小程序端根本发不出 PATCH 请求（社区里大量人踩过这个坑）。
# 两条入口指向同一个函数、同一套 exclude_unset 逻辑，行为完全一致。
@router.patch("/spaces/{space_id}/recipes/{recipe_id}", summary="修改菜谱")
@router.post(
    "/spaces/{space_id}/recipes/{recipe_id}",
    summary="修改菜谱（小程序端入口）",
    description=(
        "与 PATCH 行为完全一致，仅因微信小程序的 wx.request 不支持 PATCH 而额外开放。"
        "小程序端请使用本入口，App / H5 端用标准的 PATCH。"
    ),
)
async def update_recipe(
    space_id: int,
    recipe_id: int,
    payload: RecipeUpdateRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """修改菜谱（部分更新）。

    用 PATCH 的语义而不是 PUT，因为前端只改一个"做法"时不该把整条菜谱重传一遍；
    exclude_unset 把"请求体里真正出现过的字段"取出来交给 Service，
    于是"没传的字段保持原值"和"显式传 null 表示清空"这两种意图能区分开。
    """
    service = _build_service(session)
    recipe, nickname, category_name = await service.update_recipe(
        current_user,
        space_id,
        recipe_id,
        payload.model_dump(exclude_unset=True),
    )
    await session.commit()
    return success(_to_recipe_info(recipe, nickname, category_name).model_dump())


@router.delete("/spaces/{space_id}/recipes/{recipe_id}", summary="删除菜谱")
async def delete_recipe(
    space_id: int,
    recipe_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """删除菜谱。

    本版本不限制"只能删自己加的"（理由见 RecipeService 顶部说明），
    所以接口这里也没有额外的身份判断；将来要收紧，在 Service 里加一处即可。
    """
    service = _build_service(session)
    await service.delete_recipe(current_user, space_id, recipe_id)
    await session.commit()
    return success(message="已删除")
