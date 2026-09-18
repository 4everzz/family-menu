"""家庭提醒接口。

接口层保持"薄"：只做收参数、调 Service、返回结果。规则都在 Service 层。

提醒和家庭冰箱是同一共享域，可见范围由"是不是家庭成员"决定，判断全在后端。
"""

from datetime import date

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.response import success
from app.repositories.category_repo import CategoryRepository
from app.repositories.fridge_repo import FridgeRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.space_repo import SpaceRepository
from app.schemas.alert import AlertResponse
from app.services.alert_service import AlertService
from app.services.space_service import SpaceService

router = APIRouter(tags=["提醒"])


def _build_service(session: AsyncSession) -> AlertService:
    """组装提醒服务。复用 SpaceService 做成员校验，鉴权只有一份实现。

    CategoryRepository 是 SpaceService 构造所需的（建家庭组时用），提醒不调用建组，
    传一个实例进去只是满足依赖装配，不会真正用到。
    """
    space_service = SpaceService(SpaceRepository(session), CategoryRepository(session))
    return AlertService(FridgeRepository(session), space_service, OrderRepository(session))


@router.get("/spaces/{space_id}/alerts", summary="家庭提醒列表")
async def list_alerts(
    space_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """列出当前家庭组需要提醒的事项（冰箱临期/过期 + 缺货 + 今日未点单）。"""
    service = _build_service(session)
    alerts = await service.list_alerts(current_user, space_id, date.today())
    return success({"items": [a.model_dump() for a in alerts]})
