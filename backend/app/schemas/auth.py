"""登录相关的请求与响应模型。"""

from pydantic import BaseModel, Field

from app.schemas.user import UserInfo


class LoginRequest(BaseModel):
    """登录请求。"""

    code: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="小程序 wx.login() 返回的临时登录凭证，只能用一次且 5 分钟内有效",
    )


class LoginResponse(BaseModel):
    """登录响应。"""

    token: str = Field(..., description="访问令牌，后续请求放在请求头 Authorization: Bearer <令牌>")
    token_type: str = Field(default="Bearer", description="令牌类型")
    expires_in: int = Field(..., description="有效期（秒）")
    user: UserInfo = Field(..., description="用户信息")
