"""个人收藏接口。

⚠️ 路由顺序：`/favorites/partitions` 和 `/favorites/recipe-ids` 必须写在
`/favorites/{recipe_id}` **之前**——否则 "partitions" 会被当成 recipe_id
去解析（int 转换失败直接 422），这是 FastAPI 按声明顺序匹配的规则。
家庭组的 /spaces/quota 也是同样的坑，见 spaces.py 的说明。
"""

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.response import success
from app.repositories.category_repo import CategoryRepository
from app.repositories.favorite_repo import FavoriteRepository
from app.repositories.space_repo import SpaceRepository
from app.schemas.favorite import (
    FavoriteListResponse,
    FavoriteRecipeItem,
    FavoriteToggleRequest,
    PartitionCreateRequest,
    PartitionInfo,
)
from app.services.favorite_service import FavoriteService
from app.services.space_service import SpaceService

router = APIRouter(tags=["收藏"])


def _build_service(session: DbSession) -> FavoriteService:
    """组装收藏服务。

    收藏要复用"是不是这个家的人"这道校验（收藏前得先能看到那道菜），
    所以这里把 SpaceService 一起组装进来，三者共用同一个 session、同一个事务。
    """
    space_service = SpaceService(SpaceRepository(session), CategoryRepository(session))
    return FavoriteService(FavoriteRepository(session), space_service)


def _to_partition_info(data: tuple[int | None, str, int, bool]) -> PartitionInfo:
    """把 Service 返回的 (id, 名字, 数量, 是否默认) 转成响应模型。"""
    partition_id, name, count, is_default = data
    return PartitionInfo(id=partition_id, name=name, count=count, isDefault=is_default)


@router.get("/favorites/partitions", summary="收藏分区列表")
async def list_partitions(current_user: CurrentUser, session: DbSession) -> dict:
    """列出我的收藏分区。默认收藏夹永远在第一位、永远存在，即使下面一道菜都没有。"""
    service = _build_service(session)
    data = await service.list_partitions(current_user)
    return success([_to_partition_info(item).model_dump() for item in data])


@router.post("/favorites/partitions", summary="新建收藏分区")
async def create_partition(
    payload: PartitionCreateRequest, current_user: CurrentUser, session: DbSession
) -> dict:
    """新建一个自定义分区，排在最后。数量有上限（可在配置里调）。"""
    service = _build_service(session)
    data = await service.create_partition(current_user, payload.name)
    await session.commit()
    return success(_to_partition_info(data).model_dump())


@router.delete("/favorites/partitions/{partition_id}", summary="删除收藏分区")
async def delete_partition(
    partition_id: int, current_user: CurrentUser, session: DbSession
) -> dict:
    """删除自定义分区。里面的收藏会退回默认收藏夹（收藏本身不丢）。"""
    service = _build_service(session)
    moved = await service.delete_partition(current_user, partition_id)
    await session.commit()
    return success({"moved": moved})


@router.get("/favorites/recipe-ids", summary="我在某个家庭组里已收藏的菜谱 ID")
async def list_favorited_recipe_ids(
    space_id: int, current_user: CurrentUser, session: DbSession
) -> dict:
    """菜单页画星标用：只返回 ID 列表，一次轻量查询。"""
    service = _build_service(session)
    ids = await service.list_favorited_recipe_ids(current_user, space_id)
    return success(ids)


@router.get("/favorites", summary="收藏列表")
async def list_favorites(
    current_user: CurrentUser,
    session: DbSession,
    partition_id: int | None = Query(
        default=None,
        description="分区 ID。不传 = 默认收藏夹（它不是一行数据，所以没有'全部'的取法）",
    ),
) -> dict:
    """列出某分区下的收藏，带上菜谱摘要和家庭组名，按收藏时间倒序。"""
    service = _build_service(session)
    rows = await service.list_favorites(current_user, partition_id)
    items = [
        FavoriteRecipeItem(
            recipeId=favorite.recipe_id,
            name=recipe.name,
            description=recipe.description,
            image_url=recipe.image_url,
            spaceId=recipe.space_id,
            spaceName=space_name,
            categoryName=category_name,
            partitionId=favorite.partition_id,
            favoritedAt=favorite.created_at,
        )
        for favorite, recipe, space_name, category_name in rows
    ]
    response = FavoriteListResponse(favorites=items, total=len(items))
    return success(response.model_dump())


@router.post("/favorites/{recipe_id}", summary="收藏一道菜")
async def favorite_recipe(
    recipe_id: int,
    payload: FavoriteToggleRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """收藏一道菜；若已收藏，则把收藏挪到指定的分区（partition_id 不传即默认收藏夹）。"""
    service = _build_service(session)
    data = await service.favorite(current_user, recipe_id, payload.partition_id)
    await session.commit()
    recipe_id_, partition_id_, created = data
    return success({"recipeId": recipe_id_, "partitionId": partition_id_, "created": created})


@router.delete("/favorites/{recipe_id}", summary="取消收藏")
async def unfavorite_recipe(recipe_id: int, current_user: CurrentUser, session: DbSession) -> dict:
    """取消收藏。没收藏过会返回 404——前端的双重点击不该被静默吞掉。"""
    service = _build_service(session)
    await service.unfavorite(current_user, recipe_id)
    await session.commit()
    return success({"recipeId": recipe_id})
