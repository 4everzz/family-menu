"""家庭冰箱接口。

接口层保持"薄"：只做三件事——收参数、调 Service、返回结果。
规则和校验都在 Service 层，这样同一个规则不会因为多个接口各写一遍而出现不一致。

关于"修改"用 PUT 而不是 PATCH：
    微信小程序的 wx.request 官方 method 合法值里**没有 PATCH**，只有 PUT。
    所以这里直接用 PUT 做部分更新（接口层用 exclude_unset 取真正传来的字段），
    不必像菜谱那样再开一个 POST 副本绕开小程序限制。
"""

from datetime import date, timedelta

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.response import success
from app.models.fridge_item import FridgeItem
from app.repositories.category_repo import CategoryRepository
from app.repositories.fridge_repo import FridgeRepository
from app.repositories.space_repo import SpaceRepository
from app.schemas.fridge import FridgeItemCreateRequest, FridgeItemInfo, FridgeItemUpdateRequest
from app.services.fridge_service import EXPIRING_WITHIN_DAYS, FridgeService
from app.services.space_service import SpaceService

router = APIRouter(tags=["家庭冰箱"])


def _build_service(session: AsyncSession) -> FridgeService:
    """组装冰箱服务。复用 SpaceService 做成员/创建人校验，鉴权只有一份实现。

    CategoryRepository 是 SpaceService 构造所需的（建家庭组时用），冰箱不调用建组，
    传一个实例进去只是满足类型与依赖装配，不会真正用到。
    """
    space_service = SpaceService(SpaceRepository(session), CategoryRepository(session))
    return FridgeService(FridgeRepository(session), space_service)


def _to_info(item: FridgeItem, nickname: str) -> FridgeItemInfo:
    """把数据库对象组装成前端要的结构，并算出是否临期。"""
    is_expiring = (
        item.expiry_date is not None
        and item.expiry_date <= date.today() + timedelta(days=EXPIRING_WITHIN_DAYS)
    )
    return FridgeItemInfo(
        id=item.id,
        space_id=item.space_id,
        name=item.name,
        quantity=item.quantity,
        unit=item.unit,
        category=item.category,
        storage=item.storage,
        expiry_date=item.expiry_date,
        note=item.note,
        is_expiring=is_expiring,
        created_by=item.created_by,
        created_by_nickname=nickname,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/spaces/{space_id}/fridge", summary="家庭冰箱列表")
async def list_fridge(
    space_id: int,
    current_user: CurrentUser,
    session: DbSession,
    category: str | None = Query(default=None, max_length=16, description="按分类筛选"),
    storage: str | None = Query(default=None, max_length=8, description="按存放位置筛选"),
    keyword: str | None = Query(default=None, max_length=64, description="按食材名或备注模糊搜索"),
) -> dict:
    """列出当前家庭组的冰箱食材，顶部附带"临期件数"提示。"""
    service = _build_service(session)
    rows, expiring_count = await service.list_items(
        current_user, space_id, category, storage, keyword
    )
    return success(
        {
            "items": [_to_info(item, nickname).model_dump() for item, nickname in rows],
            "expiring_count": expiring_count,
        }
    )


@router.post("/spaces/{space_id}/fridge", summary="新增食材")
async def create_item(
    space_id: int,
    payload: FridgeItemCreateRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """在指定家庭组里新增一件食材（仅创建人）。"""
    service = _build_service(session)
    item = await service.create_item(
        current_user,
        space_id,
        name=payload.name,
        quantity=payload.quantity,
        unit=payload.unit,
        category=payload.category,
        storage=payload.storage,
        expiry_date=payload.expiry_date,
        note=payload.note,
    )
    await session.commit()
    return success(_to_info(item, current_user.nickname).model_dump())


@router.get("/spaces/{space_id}/fridge/{item_id}", summary="食材详情")
async def get_item(
    space_id: int,
    item_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """查看单条食材。必须是该家庭成员，且这条食材确实属于这个家。"""
    service = _build_service(session)
    item, nickname = await service.get_item(current_user, space_id, item_id)
    return success(_to_info(item, nickname).model_dump())


@router.put("/spaces/{space_id}/fridge/{item_id}", summary="修改食材")
async def update_item(
    space_id: int,
    item_id: int,
    payload: FridgeItemUpdateRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """修改食材（部分更新，仅创建人）。

    用 PUT 而不是 PATCH：微信小程序 wx.request 不支持 PATCH，但支持 PUT，
    所以从前端直接发 PUT 即可，不需要像菜谱那样再开 POST 副本。
    exclude_unset 把"请求体里真正出现过的字段"取出来交给 Service，
    "没传的字段保持原值"和"显式传 null 表示清空"两种意图能区分开。
    """
    service = _build_service(session)
    item = await service.update_item(
        current_user,
        space_id,
        item_id,
        payload.model_dump(exclude_unset=True),
    )
    await session.commit()
    return success(_to_info(item, current_user.nickname).model_dump())


@router.delete("/spaces/{space_id}/fridge/{item_id}", summary="删除食材")
async def delete_item(
    space_id: int,
    item_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """删除食材（仅创建人）。"""
    service = _build_service(session)
    await service.delete_item(current_user, space_id, item_id)
    await session.commit()
    return success(message="已删除")
