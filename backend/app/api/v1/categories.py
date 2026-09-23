"""家庭菜谱分类接口。

接口层保持"薄"：只做三件事——收参数、调 Service、返回结果。
规则和校验都在 Service 层，这样同一个规则不会因为多个接口各写一遍而出现不一致。

路径挂在 /spaces/{space_id}/ 下面，是因为分类属于家庭组：
"这个家的分类有哪些"天然要带上"哪个家"。同时这也让中间件和阅读代码的人
一眼看出：这些接口的数据范围都被家庭组圈住了，不存在"跨家庭组读分类"的可能。
"""

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.response import success
from app.models.recipe_category import DEFAULT_CATEGORY_NAME, RecipeCategory
from app.repositories.category_repo import CategoryRepository
from app.repositories.space_repo import SpaceRepository
from app.schemas.category import CategoryCreateRequest, CategoryInfo, CategoryReorderRequest, CategoryUpdateRequest
from app.services.category_service import CategoryService
from app.services.space_service import SpaceService

router = APIRouter(tags=["菜谱分类"])


def _build_service(session: AsyncSession) -> CategoryService:
    """组装分类服务。

    分类的可见范围由"是不是这个家的人"决定，所以把 SpaceService 注入进去，
    而不是在分类服务里再写一遍"查成员表"的逻辑——鉴权只有一份实现，才不会漏。

    注意两个服务共用同一个 CategoryRepository 实例：
    它俩本来就该看同一份数据，各自 new 一个是没必要的开销，
    也容易在将来被人误以为"这是两份独立的数据"。
    """
    category_repo = CategoryRepository(session)
    space_service = SpaceService(SpaceRepository(session), category_repo)
    return CategoryService(category_repo, space_service)


def _to_category_info(category: RecipeCategory, recipe_count: int) -> CategoryInfo:
    """把数据库对象组装成前端要的结构。"""
    return CategoryInfo(
        id=category.id,
        space_id=category.space_id,
        name=category.name,
        sort_order=category.sort_order,
        recipe_count=recipe_count,
        # "新增菜品时默认选哪个分类"由后端说了算，前端照用。
        # 前端自己硬编码一个分类名的话，用户把这个分类改个名，默认选中就失效了，
        # 而且是那种不会报错、只是悄悄不好用的失效。
        is_default=category.name == DEFAULT_CATEGORY_NAME,
    )


@router.get("/spaces/{space_id}/categories", summary="家庭菜谱分类列表")
async def list_categories(space_id: int, current_user: CurrentUser, session: DbSession) -> dict:
    """列出当前家庭组的全部分类，带每个分类下的菜谱数量。

    顺序由后端给（sort_order 升序），前端侧边栏直接照用。
    如果让前端自己排，两边各有一套顺序，迟早会走偏。
    """
    service = _build_service(session)
    rows = await service.list_categories(current_user, space_id)
    return success([_to_category_info(category, count).model_dump() for category, count in rows])


@router.post("/spaces/{space_id}/categories", summary="新增分类")
async def create_category(
    space_id: int,
    payload: CategoryCreateRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """在指定家庭组里新增一个分类，排在现有分类的最后面。"""
    service = _build_service(session)
    category = await service.create_category(current_user, space_id, payload.name)
    await session.commit()
    # 新建的分类下面一道菜都没有，所以数量固定是 0
    return success(_to_category_info(category, 0).model_dump())


@router.post("/spaces/{space_id}/categories/reorder", summary="调整分类顺序")
async def reorder_categories(
    space_id: int,
    payload: CategoryReorderRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """保存当前家庭的完整分类顺序，避免部分提交造成重复或断档。"""
    service = _build_service(session)
    rows = await service.reorder_categories(current_user, space_id, payload.category_ids)
    await session.commit()
    return success([_to_category_info(category, count).model_dump() for category, count in rows])


# 同一个处理函数挂两个路由，原因是平台限制，不是设计冗余：
#   PATCH 是标准写法，留给将来打包成 App / H5 的客户端；
#   POST  是为了绕开微信小程序——wx.request 的 method 合法值里没有 PATCH，
#         小程序端根本发不出 PATCH 请求。
# 两条入口指向同一个函数，行为完全一致。
@router.patch("/spaces/{space_id}/categories/{category_id}", summary="修改分类")
@router.post(
    "/spaces/{space_id}/categories/{category_id}",
    summary="修改分类（小程序端入口）",
    description=(
        "与 PATCH 行为完全一致，仅因微信小程序的 wx.request 不支持 PATCH 而额外开放。"
        "小程序端请使用本入口，App / H5 端用标准的 PATCH。"
    ),
)
async def update_category(
    space_id: int,
    category_id: int,
    payload: CategoryUpdateRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """修改分类（目前只支持改名）。"""
    service = _build_service(session)
    category = await service.rename_category(current_user, space_id, category_id, payload.name)
    await session.commit()
    # 改名不影响菜品归属，数量照原样查一次返回，让前端拿到的结构和列表接口一致
    recipe_count = await service.count_recipes(category.id)
    return success(_to_category_info(category, recipe_count).model_dump())


@router.delete("/spaces/{space_id}/categories/{category_id}", summary="删除分类")
async def delete_category(
    space_id: int,
    category_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """删除分类。

    分类下还有菜谱时会拒绝（400），提示先把菜改到别的分类。
    理由见 CategoryService 顶部：菜谱跟着分类一起消失，等于凭空丢数据。
    """
    service = _build_service(session)
    await service.delete_category(current_user, space_id, category_id)
    await session.commit()
    return success(message="已删除")
