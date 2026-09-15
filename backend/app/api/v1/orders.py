"""点单接口。

接口层保持"薄"：只做收参数、调 Service、返回结果，规则全在 Service 层。

关于"改状态"用 PUT 而不是 PATCH：
    微信小程序的 wx.request 官方 method 合法值里**没有 PATCH**，只有 PUT。
    这里要改的本来也只有一个 status 字段，用 PUT 语义上说得通，
    也就不必像菜谱那样再开一个行为相同的 POST 副本绕开小程序限制（冰箱也是这么做的）。
"""

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.response import success
from app.models.dish_order import DishOrder, DishOrderItem
from app.repositories.category_repo import CategoryRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.space_repo import SpaceRepository
from app.schemas.order import (
    ALLOWED_STATUSES,
    OrderCreateRequest,
    OrderInfo,
    OrderItemInfo,
    OrderStatusUpdateRequest,
)
from app.services.order_service import OrderService
from app.services.space_service import SpaceService

router = APIRouter(tags=["点单"])


def _build_service(session: AsyncSession) -> OrderService:
    """组装点单服务。复用 SpaceService 做成员/创建人校验，鉴权只有一份实现。

    CategoryRepository 是 SpaceService 构造所需的（建家庭组时用），
    点单不调用建组，传进去只是满足依赖装配，不会真正用到。
    """
    space_service = SpaceService(SpaceRepository(session), CategoryRepository(session))
    return OrderService(OrderRepository(session), space_service)


def _to_info(
    order: DishOrder,
    nickname: str,
    items: list[DishOrderItem],
    *,
    can_manage: bool,
) -> OrderInfo:
    """把数据库对象组装成前端要的结构。

    dish_count 和 total_quantity 由后端算好：
    前端列表上要显示"共 5 道 / 7 份"，让它自己在模板里循环求和既啰嗦又容易算错。

    can_manage 同理——它是"创建人 或 提交者本人"，前端不该自己判断。
    """
    item_infos = [OrderItemInfo.model_validate(item) for item in items]
    return OrderInfo(
        id=order.id,
        space_id=order.space_id,
        created_by=order.created_by,
        created_by_nickname=nickname,
        guest_name=order.guest_name,
        remark=order.remark,
        status=order.status,
        created_at=order.created_at,
        can_manage=can_manage,
        items=item_infos,
        dish_count=len(item_infos),
        total_quantity=sum(item.quantity for item in item_infos),
    )


@router.get("/spaces/{space_id}/orders", summary="点单列表")
async def list_orders(
    space_id: int,
    current_user: CurrentUser,
    session: DbSession,
    status: str | None = Query(
        default=None,
        description=f"按状态筛选：{' 或 '.join(ALLOWED_STATUSES)}；不传表示全部",
    ),
) -> dict:
    """列出这个家的点单。任何家庭成员都能看。

    传 status=pending 可以只看"还没做的"，这是创建人最常用的视角。
    """
    service = _build_service(session)
    rows, is_owner = await service.list_orders(current_user, space_id, status)
    return success(
        [
            _to_info(
                order,
                nickname,
                items,
                # 创建人能管所有人的单；其他人只能管自己提交的
                can_manage=is_owner or order.created_by == current_user.id,
            ).model_dump()
            for order, nickname, items in rows
        ]
    )


@router.post("/spaces/{space_id}/orders", summary="提交点单")
async def create_order(
    space_id: int,
    payload: OrderCreateRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """提交一张点单。

    任何家庭成员都能提交——点单是"提需求"，不是"改菜单"。
    客人拿创建人手机点单时，提交者记的就是创建人，客人名字填在 guest_name 里（可不填）。
    """
    service = _build_service(session)
    order, items = await service.create_order(
        current_user,
        space_id,
        guest_name=payload.guest_name,
        remark=payload.remark,
        items=[(item.recipe_id, item.quantity, item.spice) for item in payload.items],
    )
    await session.commit()
    await session.refresh(order)
    # 刚提交的单一定是自己的，管理权不用再算
    return success(_to_info(order, current_user.nickname, items, can_manage=True).model_dump())


@router.put("/spaces/{space_id}/orders/{order_id}", summary="修改点单状态")
async def update_order_status(
    space_id: int,
    order_id: int,
    payload: OrderStatusUpdateRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """把点单标记成「已完成」或撤回成「待处理」。

    权限：提交者本人，或者这个家的创建人。
    """
    service = _build_service(session)
    # nickname 用 Service 查出来的**提交者**昵称，而不是 current_user.nickname：
    # 创建人可以管成员提交的单，这时两者不是同一个人
    order, nickname, items = await service.update_status(
        current_user, space_id, order_id, payload.status
    )
    await session.commit()
    await session.refresh(order)
    # 能改就说明有权限（Service 已经校验过），所以恒为 true
    return success(_to_info(order, nickname, items, can_manage=True).model_dump())


@router.delete("/spaces/{space_id}/orders/{order_id}", summary="删除点单")
async def delete_order(
    space_id: int,
    order_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """删除一张点单，明细一起删掉。

    权限：提交者本人，或者这个家的创建人。
    """
    service = _build_service(session)
    await service.delete_order(current_user, space_id, order_id)
    await session.commit()
    return success(None)
