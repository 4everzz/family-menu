"""用户相关的数据模型。"""

from pydantic import BaseModel, ConfigDict, Field


class UserInfo(BaseModel):
    """返回给前端的用户信息。

    这里刻意只暴露必要字段：
    - openid / unionid 属于微信身份标识，前端不需要，给了反而是泄露面；
    - is_active 这类内部状态同理。

    from_attributes=True 表示可以直接把数据库对象（ORM 对象）转成这个模型，
    不用手工一个个字段去取。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="用户 ID")
    nickname: str = Field(..., description="昵称")
    avatar_url: str | None = Field(default=None, description="头像地址（微信临时链接，会过期）")
