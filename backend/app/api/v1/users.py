"""用户类接口。

目前两个能力：
    GET   /users/me   读当前登录用户
    PATCH /users/me   改当前登录用户的个人资料（昵称、头像）

⚠️ 路径里没有 {user_id}，一律用 "me"。这是有意的：
   身份从令牌里解析，前端既不需要也传不了"我要改谁"。
   只要路径里能传 ID，就有人会传别人的 ID 去改别人的资料——
   把这种可能性从接口形状上消掉，比在每个接口里写一遍校验可靠得多。
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.response import success
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserInfo, UserUpdateRequest
from app.services.user_service import UserService

router = APIRouter(tags=["用户"])


@router.get("/users/me", summary="获取当前登录用户")
async def get_me(current_user: CurrentUser) -> dict:
    """返回当前登录用户信息。

    需要登录：请求头必须带 Authorization: Bearer <令牌>。
    用户身份从令牌解析，前端不需要（也不能）自己传用户 ID——
    否则传别人的 ID 就能读到别人的数据了。
    """
    return success(UserInfo.model_validate(current_user).model_dump())


@router.patch("/users/me", summary="修改个人资料")
@router.post(
    "/users/me",
    summary="修改个人资料（小程序端入口）",
    description=(
        "与 PATCH 行为完全一致，仅因微信小程序的 wx.request 不支持 PATCH 而额外开放。"
        "小程序端请使用本入口，App / H5 端用标准的 PATCH。"
    ),
)
async def update_me(
    payload: UserUpdateRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """修改当前登录用户的昵称 / 头像（部分更新）。

    用 PATCH 而不是 PUT：改个昵称不该把头像也重传一遍。
    exclude_unset 把"请求体里真正出现过的字段"取出来交给 Service，
    于是"没传的字段保持原值"和"显式传 null 表示清空"这两种意图能区分开——
    头像传 null 就是"撤销自定义头像，回到默认占位图"。

    传了个空对象（什么都不改）会被拒绝，而不是静默返回成功：
    那多半是前端漏传了字段，早点报出来比让用户以为改成功了要好。
    """
    service = UserService(UserRepository(session))
    user = await service.update_profile(current_user, payload.model_dump(exclude_unset=True))

    await session.commit()
    return success(UserInfo.model_validate(user).model_dump())
