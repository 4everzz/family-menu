"""注册与登录的业务规则。

本文件有两条互相独立的登录链路：

    1. 自建账号（主链路）
       "用户名 + 密码" → 取出库里的 password_hash 比对 → 签发令牌。
       不依赖任何第三方平台，App / H5 / 小程序三端行为完全一致，所以是主干。

    2. 微信小程序静默登录（保留）
       小程序里 uni.login() 拿到临时 code → 后端用 code + AppSecret 去微信换 openid
       → 按 (provider='wx_mp', openid) 查 user_identities → 查到就登录，查不到就建号。
       ⚠️ 这条路**只在微信小程序端有效**。App 端要接微信登录，需要微信开放平台的
       「移动应用」+ 企业认证（300 元/年，个人开发者申请不了），所以 App 上不用它。
       保留它的原因：它免费、无需用户输入，而且改造前的老用户只有这一条路能进来。

为什么 AppSecret 不能放前端？
    它相当于小程序的"身份密钥"。放在前端一旦被反编译拿到，
    别人就能冒充你的小程序去调用微信接口，这是严重的身份泄露。
"""

import logging
from dataclasses import dataclass

import httpx
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.exceptions import BusinessError
from app.core.password import hash_password, verify_password
from app.core.response import (
    CODE_ACCOUNT_DISABLED,
    CODE_BAD_CREDENTIALS,
    CODE_USERNAME_TAKEN,
    CODE_WX_LOGIN_FAILED,
    CODE_WX_NOT_CONFIGURED,
    CODE_WX_UNAVAILABLE,
)
from app.core.security import create_access_token
from app.models.user import User
from app.models.user_identity import PROVIDER_WX_MP
from app.repositories.user_identity_repo import UserIdentityRepository
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)

# 微信换取 openid 的官方接口
WX_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"

# 登录失败时的统一文案。用户不存在和密码错误必须说同一句话，见 login_with_password 的说明。
_BAD_CREDENTIALS_MESSAGE = "用户名或密码不正确"


@dataclass(frozen=True)
class WxSession:
    """微信 code2Session 返回的关键信息。

    只留我们真正要用的两个字段：
        openid —— 用户在这个小程序里的唯一标识，登录时按它找账号；
        unionid —— 跨应用识别同一个人用的，只有绑定了微信开放平台才会返回，通常为空。
    响应里的 session_key 用于解密用户敏感数据（手机号、昵称头像授权），本项目用不到，
    刻意不接收、不保存——少存一份密钥就少一个泄露面。
    """

    openid: str
    unionid: str | None


class AuthService:
    """注册与登录服务。"""

    def __init__(self, repo: UserRepository, identity_repo: UserIdentityRepository) -> None:
        self.repo = repo
        self.identity_repo = identity_repo

    # ==================== 自建账号：注册 ====================

    async def register(self, username: str, password: str) -> tuple[User, str]:
        """注册一个"用户名 + 密码"的账号，并直接返回登录令牌。

        返回：(用户对象, 访问令牌)
        注册完直接把令牌发出去，而不是让用户再输一遍密码——这个体量的产品该有的顺手程度。

        ⚠️ 这里**不接收昵称等个人资料**：注册只负责"把账号建出来"，
           用户想改昵称、换头像要去「我的」页（见 api/v1/users.py 的更新接口）。
           注册表单每多一个字段，放弃注册的人就多一分。
        """
        # 先查一次，目的只是给出"用户名已被占用"这种具体、可操作的提示。
        # 但它不能当作唯一防线：两个请求可能同时查到"没占用"，然后各插一行。
        # 真正的保证是 users.username 上的唯一索引，见下面捕获 IntegrityError 的位置。
        if await self.repo.get_by_username(username) is not None:
            raise BusinessError("该用户名已被占用，换一个试试", code=CODE_USERNAME_TAKEN)

        try:
            user = await self.repo.create_local_user(
                username=username,
                password_hash=hash_password(password),
            )
        except IntegrityError as exc:
            # 走到这里说明正好撞上了并发注册：两个请求同时注册同一个用户名，
            # 其中一个被数据库的唯一索引挡了下来——这正是它存在的意义。
            # 事务已经失败，必须先回滚，否则这个会话后续任何语句都会报错。
            await self.repo.session.rollback()
            logger.info("并发注册撞上唯一索引 | username=%s", username)
            raise BusinessError("该用户名已被占用，换一个试试", code=CODE_USERNAME_TAKEN) from exc

        logger.info("新账号注册 | id=%s | username=%s", user.id, username)
        return user, create_access_token(user.id)

    # ==================== 自建账号：登录 ====================

    async def login_with_password(self, username: str, password: str) -> tuple[User, str]:
        """用户名 + 密码登录。返回 (用户对象, 访问令牌)。"""
        user = await self.repo.get_by_username(username)

        # ⚠️ "用户不存在"和"密码错误"必须返回同一句话，这是有意的。
        # 如果分开提示（"该用户不存在" / "密码错误"），
        # 攻击者就能拿一批用户名来试探，从提示语的差别里筛出哪些账号真实存在，
        # 再只针对存在的那些去爆破——相当于免费送他一份有效用户名清单。
        if user is None or not verify_password(password, user.password_hash):
            raise BusinessError(_BAD_CREDENTIALS_MESSAGE, code=CODE_BAD_CREDENTIALS)

        self._ensure_active(user)
        logger.info("密码登录成功 | id=%s", user.id)
        return user, create_access_token(user.id)

    # ==================== 微信小程序静默登录 ====================

    async def login_with_wechat(self, code: str) -> tuple[User, str]:
        """微信小程序登录。首次登录会自动建号。返回 (用户对象, 访问令牌)。"""
        session = await self._resolve_wechat_session(code)

        identity = await self.identity_repo.get_by_external_id(PROVIDER_WX_MP, session.openid)
        if identity is None:
            # 这个 openid 第一次出现：建一个"只有微信身份"的用户。
            # 他暂时没有用户名和密码，所以还登不了 App；
            # 将来在「我的」里补设一套账号密码之后，两端就能用同一个账号了（后续功能）。
            user = await self.repo.create_wechat_user()
            await self.identity_repo.create(
                user_id=user.id,
                provider=PROVIDER_WX_MP,
                external_id=session.openid,
                unionid=session.unionid,
            )
            logger.info("微信新用户自动注册 | id=%s", user.id)
        else:
            # 这次微信给了 unionid 而库里还没有，顺手补上。
            # 什么时候会这样：用户当初只授权了小程序（拿不到 unionid），
            # 后来我们才绑定微信开放平台。补上之后跨应用识别同一人才生效。
            if session.unionid and identity.unionid != session.unionid:
                identity.unionid = session.unionid

            user = await self.repo.get_by_id(identity.user_id)
            if user is None:
                # 正常不会发生：user_identities.user_id 有外键约束兜着。
                # 真出现说明数据被人为改坏了，明确报错比返回一个空对象好排查。
                logger.error("身份绑定的用户不存在 | identity_id=%s", identity.id)
                raise BusinessError("登录信息异常，请重新登录", code=CODE_BAD_CREDENTIALS)

        self._ensure_active(user)
        return user, create_access_token(user.id)

    # ==================== 内部方法 ====================

    @staticmethod
    def _ensure_active(user: User) -> None:
        """账号被停用就不允许登录。

        放在签发令牌之前：令牌一旦发出去就没法收回了（服务端不存会话），
        所以必须在发之前拦住。
        """
        if not user.is_active:
            raise BusinessError(
                "账号已被停用，请联系管理员",
                code=CODE_ACCOUNT_DISABLED,
                http_status=403,
            )

    async def _resolve_wechat_session(self, code: str) -> WxSession:
        """把临时 code 换成微信会话信息。

        开发模式（AUTH_DEV_MODE=true）下跳过微信校验，直接用固定 openid，
        目的是在还没拿到 AppSecret 时也能把整条链路先跑通。
        该开关默认关闭，且生产环境启动时会直接拒绝（见 core/config.py）。
        """
        if settings.auth_dev_mode:
            logger.warning("开发模式生效：跳过微信校验，使用固定 openid=%s", settings.auth_dev_openid)
            return WxSession(openid=settings.auth_dev_openid, unionid=None)

        if not settings.wx_appid or not settings.wx_secret:
            raise BusinessError(
                "服务端尚未配置微信 AppSecret，无法完成登录",
                code=CODE_WX_NOT_CONFIGURED,
                http_status=500,
            )

        payload = await self._call_wx_code2session(code)

        openid = payload.get("openid")
        if not openid:
            # 常见错误：40029 code 无效、45011 频率限制、40226 高风险用户被拦截
            errcode = payload.get("errcode")
            errmsg = payload.get("errmsg", "未知错误")
            logger.warning("微信登录失败 | errcode=%s | errmsg=%s", errcode, errmsg)
            raise BusinessError(
                f"微信登录失败（错误码 {errcode}）：{errmsg}",
                code=CODE_WX_LOGIN_FAILED,
                http_status=400,
            )

        return WxSession(openid=openid, unionid=payload.get("unionid"))

    async def _call_wx_code2session(self, code: str) -> dict:
        """调用微信接口换取 openid。网络异常统一转成可读的业务错误。"""
        params = {
            "appid": settings.wx_appid,
            "secret": settings.wx_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(WX_CODE2SESSION_URL, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            logger.error("调用微信 code2Session 失败: %s", exc)
            raise BusinessError(
                "微信服务暂时不可用，请稍后重试",
                code=CODE_WX_UNAVAILABLE,
                http_status=502,
            ) from exc
