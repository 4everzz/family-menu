"""用户类接口。"""

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.response import success
from app.schemas.user import UserInfo

router = APIRouter(tags=["用户"])


@router.get("/users/me", summary="获取当前登录用户")
async def get_me(current_user: CurrentUser) -> dict:
    """返回当前登录用户信息。

    需要登录：请求头必须带 Authorization: Bearer <令牌>。
    用户身份从令牌解析，前端不需要（也不能）自己传用户 ID——
    否则传别人的 ID 就能读到别人的数据了。
    """
    return success(UserInfo.model_validate(current_user).model_dump())
