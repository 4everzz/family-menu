"""注册与登录接口。

三个入口的分工：
    POST /auth/register      自建账号注册 —— App / H5 / 小程序通用
    POST /auth/login         自建账号登录 —— App / H5 / 小程序通用
    POST /auth/login/wechat  微信小程序静默登录 —— 只有小程序端用得到
                             （App 端接微信登录需要企业认证，个人开发者申请不了）

"当前登录用户"这个接口不在这里，它属于用户资源，放在 api/v1/users.py 的 GET /users/me。
"""

from fastapi import APIRouter

from app.api.deps import DbSession
from app.core.config import settings
from app.core.response import success
from app.models.user import User
from app.repositories.user_identity_repo import UserIdentityRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import (
    LoginResponse,
    PasswordLoginRequest,
    RegisterRequest,
    WechatLoginRequest,
)
from app.schemas.user import UserInfo
from app.services.auth_service import AuthService

router = APIRouter(tags=["认证"])


def _build_service(session: DbSession) -> AuthService:
    """组装一次登录服务。

    两个仓储共用同一个 session，所以它们看到的是同一个事务——
    注册时要同时写 users 和 user_identities 两张表，这一点必须是原子的。
    """
    return AuthService(UserRepository(session), UserIdentityRepository(session))


def _login_payload(user: User, token: str) -> dict:
    """注册与登录共用的响应体：令牌 + 有效期 + 用户信息。

    抽出来是为了保证两条链路返回的结构一模一样，
    前端只需要写一套解析逻辑，不用为"注册"和"登录"各写一份。
    """
    result = LoginResponse(
        token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserInfo.model_validate(user),
    )
    return success(result.model_dump())


@router.post("/auth/register", summary="注册（用户名 + 密码）")
async def register(payload: RegisterRequest, session: DbSession) -> dict:
    """注册账号，并直接返回登录令牌。

    注册成功后直接进登录态，不让用户再输一次刚设好的密码。
    用户名的唯一性由数据库唯一索引保证——两个请求同时注册同一个名字时，
    一定有一个会被挡下来（详见 AuthService.register）。

    这里只收账号信息（用户名 + 密码 + 确认密码），**不收昵称头像**。
    个人资料一律登录后去「我的」页修改（见 users.py 的更新接口）。
    """
    user, token = await _build_service(session).register(payload.username, payload.password)

    # 事务边界放在接口这一层：本次注册涉及的所有写入在这里一次性提交
    await session.commit()
    await session.refresh(user)  # 取回数据库生成的 created_at 等字段
    return _login_payload(user, token)


@router.post("/auth/login", summary="登录（用户名 + 密码）")
async def login(payload: PasswordLoginRequest, session: DbSession) -> dict:
    """用户名 + 密码登录。

    用户名或密码不正确时，返回的是同一句提示（不会告诉你错的是哪一个），
    避免被用来试探哪些用户名真实存在。
    """
    user, token = await _build_service(session).login_with_password(payload.username, payload.password)
    # 登录本身不改数据，但事务里可能有过期状态需要收尾，统一提交一次
    await session.commit()
    return _login_payload(user, token)


@router.post("/auth/login/wechat", summary="微信小程序登录")
async def login_with_wechat(payload: WechatLoginRequest, session: DbSession) -> dict:
    """用小程序临时 code 换取访问令牌。

    首次登录会自动创建用户，前端不需要额外的注册流程。
    注意：这条路只在微信小程序端可用（App/H5 调不通）。
    """
    user, token = await _build_service(session).login_with_wechat(payload.code)

    # 事务边界放在接口这一层：首次登录可能同时新建了用户和身份绑定，必须一起提交
    await session.commit()
    await session.refresh(user)
    return _login_payload(user, token)
