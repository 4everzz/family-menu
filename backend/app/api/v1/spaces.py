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

    返回里每条都带 my_role：
    **admin = "我创建的"，member = "我加入的"**——
    前端就靠这个字段把列表分成两组，不用自己再判断归属。
    （创建人一定是 admin，加入的人一定是 member，所以这个字段足以区分。）
    """
    service = _build_service(session)
    rows = await service.list_my_spaces(current_user)
    return success([_to_space_info(space, role, count).model_dump() for space, role, count in rows])


@router.get("/spaces/quota", summary="我的家庭组额度")
async def get_space_quota(current_user: CurrentUser, session: DbSession) -> dict:
    """返回"我还能建几个、还能加几个"。

    前端据此在用户动手之前就说清还能不能建／加，
    而不是等他填完名字才被拒绝——那种体验最差。

    ⚠️ 路由顺序很重要：这条必须写在 `/spaces/{space_id}` **之前**，
    否则 "quota" 会被当成 space_id 去解析，直接报 422。
    """
    service = _build_service(session)
    quota, owned, joined = await service.get_quota_usage(current_user)
    return success(
        {
            "max_owned": quota.max_owned,
            "max_joined": quota.max_joined,
            "owned": owned,
            "joined": joined,
        }
    )


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


@router.post("/spaces/{space_id}/leave", summary="退出家庭组")
async def leave_space(space_id: int, current_user: CurrentUser, session: DbSession) -> dict:
    """退出家庭组。

    创建人不能直接退出——他走了这个组就没人管了，而"转让创建人"功能暂不做，
    所以要求创建人走「解散」这条路。规则在 Service 层，这里只负责翻译成响应。
    """
    service = _build_service(session)
    await service.leave_space(current_user, space_id)
    await session.commit()
    return success(message="已退出")


@router.delete("/spaces/{space_id}/members/{user_id}", summary="移除家庭成员")
async def remove_space_member(
    space_id: int,
    user_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """把某个成员移出家庭组。只有创建人能操作，且不能移除自己。

    路径里带上被移除者的 user_id，而不是"移除某个成员记录"——
    语义更清楚，而且天然要求调用方明确指定"移除谁"，
    比传一个成员记录 ID 更难被猜出来利用。
    """
    service = _build_service(session)
    await service.remove_member(current_user, space_id, user_id)
    await session.commit()
    return success(message="已移除")


@router.delete("/spaces/{space_id}", summary="解散家庭组")
async def dissolve_space(space_id: int, current_user: CurrentUser, session: DbSession) -> dict:
    """解散整个家庭组。只有创建人能操作。

    ⚠️ **不可逆**：这个家庭的成员关系、菜谱、菜谱分类会一起消失
    （由数据库外键级联完成）。前端必须做二次确认。
    """
    service = _build_service(session)
    await service.dissolve_space(current_user, space_id)
    await session.commit()
    return success(message="已解散")
