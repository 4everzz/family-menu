"""FastAPI 依赖注入：数据库会话与当前登录用户。

依赖注入（Dependency Injection）这个词听起来复杂，通俗说就是：
    接口函数不自己去"取"需要的东西，而是声明"我需要一个数据库会话、一个当前用户"，
    由框架在调用前准备好并传进来。这样接口函数只关心自己的业务，
    重复的准备工作（解析令牌、查用户）只写一遍，所有接口共用。
"""

from typing import Annotated

import jwt
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user_repo import UserRepository


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """从请求头解析令牌并取出当前用户。

    这是所有"需要登录"的接口的统一入口。
    权限判断必须放在后端：前端把按钮藏起来只是体验优化，不是安全边界，
    别人完全可以绕开界面直接调接口。
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("请先登录")

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("登录已过期，请重新登录") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("登录凭证无效") from exc

    subject = payload.get("sub")
    if not subject:
        raise UnauthorizedError("登录凭证无效")

    user = await UserRepository(session).get_by_id(int(subject))
    if user is None or not user.is_active:
        raise UnauthorizedError("账号不存在或已停用")
    return user


# 把常用依赖做成简写类型，接口里直接写 DbSession / CurrentUser 即可
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
