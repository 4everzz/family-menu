"""家庭组接口。

接口层保持"薄"：只做三件事——收参数、调 Service、返回结果。
规则和校验都在 Service 层，这样同一个规则不会因为多个接口各写一遍而出现不一致。
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.response import success
from app.models.space import ROLE_ADMIN, Space
from app.repositories.category_repo import CategoryRepository
from app.repositories.space_repo import SpaceRepository
from app.schemas.space import SpaceCreateRequest, SpaceInfo, SpaceJoinRequest, SpaceMemberInfo
from app.services.space_service import SpaceService

router = APIRouter(tags=["家庭组"])


def _build_service(session: DbSession) -> SpaceService:
    """组装家庭组服务。

    两个 Repository 共用同一个 session，所以它们处在同一个事务里——
    这意味着"建家庭组"和"建这个家的默认分类"要么一起成功，要么一起失败，
    不会出现一个没有任何分类的半成品家庭组。
    """
    return SpaceService(SpaceRepository(session), CategoryRepository(session))


def _to_space_info(space: Space, my_role: str, member_count: int) -> SpaceInfo:
    """把数据库对象组装成前端要的结构。

    关于邀请码：只对管理员返回。
    这不是"前端把字段藏起来"，而是后端根本不发这个值——
    普通成员就算直接调接口，拿到的也是 null，绕不过去。
    """
    return SpaceInfo(
        id=space.id,
        name=space.name,
        owner_id=space.owner_id,
        member_count=member_count,
        my_role=my_role,
        invite_code=space.invite_code if my_role == ROLE_ADMIN else None,
    )


@router.get("/spaces", summary="我加入的家庭组")
async def list_spaces(current_user: CurrentUser, session: DbSession) -> dict:
    """列出我创建和加入的全部家庭组。

    一个人可以有多个家庭组（比如自己家 + 父母家），
    所以前端需要提供"切换当前家庭组"的能力。
    """
    service = _build_service(session)
    rows = await service.list_my_spaces(current_user)
    return success([_to_space_info(space, role, count).model_dump() for space, role, count in rows])


@router.post("/spaces", summary="创建家庭组")
async def create_space(payload: SpaceCreateRequest, current_user: CurrentUser, session: DbSession) -> dict:
    """创建家庭组，创建者自动成为该组管理员。"""
    service = _build_service(session)
    space, my_role, member_count = await service.create_space(current_user, payload.name)

    # 事务边界放在接口层：本次创建涉及"建组 + 把创建者加为成员 + 建默认分类"三次写入，
    # 一起提交。中间任何一步失败，整个家庭组都不会被创建，避免留下半成品数据。
    await session.commit()
    return success(_to_space_info(space, my_role, member_count).model_dump())


@router.post("/spaces/join", summary="用邀请码加入家庭组")
async def join_space(payload: SpaceJoinRequest, current_user: CurrentUser, session: DbSession) -> dict:
    """凭家人分享的邀请码加入家庭组。"""
    service = _build_service(session)
    space, my_role, member_count = await service.join_space(current_user, payload.invite_code)
    await session.commit()
    return success(_to_space_info(space, my_role, member_count).model_dump())


@router.get("/spaces/{space_id}", summary="家庭组详情")
async def get_space_detail(space_id: int, current_user: CurrentUser, session: DbSession) -> dict:
    """查看某个家庭组的详情。必须先是该组成员。"""
    service = _build_service(session)
    space, my_role, member_count = await service.get_space_detail(current_user, space_id)
    return success(_to_space_info(space, my_role, member_count).model_dump())


@router.get("/spaces/{space_id}/members", summary="家庭成员列表")
async def list_space_members(space_id: int, current_user: CurrentUser, session: DbSession) -> dict:
    """列出家庭成员。必须先是该组成员，否则返回 403。"""
    service = _build_service(session)
    rows = await service.list_members(current_user, space_id)
    return success(
        [
            SpaceMemberInfo(
                user_id=user.id,
                nickname=user.nickname,
                avatar_url=user.avatar_url,
                role=member.role,
                is_owner=member.role == ROLE_ADMIN,
            ).model_dump()
            for member, user in rows
        ]
    )
