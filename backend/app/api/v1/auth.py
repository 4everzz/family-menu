"""登录接口。"""

from fastapi import APIRouter

from app.api.deps import DbSession
from app.core.config import settings
from app.core.response import success
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.user import UserInfo
from app.services.auth_service import AuthService

router = APIRouter(tags=["认证"])


@router.post("/auth/login", summary="微信登录")
async def login(payload: LoginRequest, session: DbSession) -> dict:
    """用小程序临时 code 换取访问令牌。

    首次登录会自动创建用户，前端不需要额外的注册流程。
    """
    service = AuthService(UserRepository(session))
    user, token = await service.login(payload.code)

    # 事务边界放在接口这一层：本次登录涉及的所有写入在这里一次性提交
    await session.commit()
    await session.refresh(user)  # 取回数据库生成的 created_at 等字段

    result = LoginResponse(
        token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserInfo.model_validate(user),
    )
    return success(result.model_dump())
