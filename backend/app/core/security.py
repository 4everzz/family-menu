"""登录令牌（JWT）的签发与校验。

通俗理解 JWT：
    它像一张盖了防伪章的通行证。服务端用密钥签个名，前端拿着它来访问接口，
    服务端验一下签名就知道"这张证确实是我发的、而且没过期"，不用每次都查数据库。
    好处是服务端不需要保存会话（无状态），横向扩容很方便。
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import settings


def create_access_token(user_id: int) -> str:
    """签发访问令牌。

    参数：
        user_id：用户主键，放入标准字段 sub（令牌主体）
    返回：
        编码后的令牌字符串

    为什么令牌里不再放 openid、用户名这些身份信息？
        令牌是"谁拿到谁就能用"的凭证，前端存在本地，内容也只是 base64 编码、并非加密，
        任何人解开都能看到。既然鉴定用过一次 sub（查数据库）就够了，
        就不要再往里塞身份细节——少一个字段就少一分泄露面。
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,  # 签发时间
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),  # 过期时间
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """校验并解析令牌。

    令牌无效或已过期时会抛出 jwt 的异常，由上层统一转换成 401 响应，
    这样各处的错误处理逻辑保持一致，不用每个接口都写一遍。
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
