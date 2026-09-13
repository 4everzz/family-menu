"""登录业务规则。

流程：
    小程序 wx.login() 拿到临时 code
        → 后端带着 code + AppSecret 去微信换 openid（这一步必须在服务端做）
        → 按 openid 查用户，没有就自动创建一个
        → 签发 JWT 返回给小程序

为什么 AppSecret 不能放前端？
    它相当于小程序的"身份密钥"。放在前端一旦被反编译拿到，
    别人就能冒充你的小程序去调用微信接口，这是严重的身份泄露。
"""

import logging

import httpx

from app.core.config import settings
from app.core.exceptions import BusinessError
from app.core.response import CODE_ACCOUNT_DISABLED, CODE_WX_LOGIN_FAILED, CODE_WX_NOT_CONFIGURED, CODE_WX_UNAVAILABLE
from app.core.security import create_access_token
from app.models.user import User
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)

# 微信换取 openid 的官方接口
WX_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class AuthService:
    """登录服务。"""

    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo

    async def login(self, code: str) -> tuple[User, str]:
        """登录入口。

        返回：
            (用户对象, 访问令牌)
        """
        openid = await self._resolve_openid(code)

        user = await self.repo.get_by_openid(openid)
        if user is None:
            # 首次登录自动注册：用户在小程序里不需要填任何表单，体验最好
            user = await self.repo.create(openid=openid)
            logger.info("新用户自动注册 | id=%s", user.id)

        if not user.is_active:
            raise BusinessError("账号已被停用，请联系管理员", code=CODE_ACCOUNT_DISABLED, http_status=403)

        token = create_access_token(user_id=user.id, openid=user.openid)
        return user, token

    async def _resolve_openid(self, code: str) -> str:
        """把临时 code 换成 openid。

        开发模式（AUTH_DEV_MODE=true）下跳过微信校验，直接使用固定 openid，
        目的是在还没拿到 AppSecret 时也能把前后端整条链路先跑通。
        该开关默认关闭，且生产环境启动时会直接拒绝（见 core/config.py）。
        """
        if settings.auth_dev_mode:
            logger.warning("开发模式生效：跳过微信校验，使用固定 openid=%s", settings.auth_dev_openid)
            return settings.auth_dev_openid

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

        # 注意：响应里的 session_key 用于解密用户敏感数据，本项目用不到，
        # 这里刻意不保存、也不返回给前端，减少泄露面。
        return openid

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
