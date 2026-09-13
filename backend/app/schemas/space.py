"""家庭组相关的请求与响应模型。"""

from pydantic import BaseModel, ConfigDict, Field


class SpaceCreateRequest(BaseModel):
    """创建家庭组请求。"""

    name: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="家庭组名称，例如「张家」「爸妈家」",
    )


class SpaceJoinRequest(BaseModel):
    """用邀请码加入家庭组请求。"""

    invite_code: str = Field(
        ...,
        min_length=4,
        max_length=16,
        description="家人分享的邀请码，不区分大小写",
    )


class SpaceInfo(BaseModel):
    """家庭组信息（返回给前端）。

    invite_code 只在当前用户是该组管理员时才有值，
    普通成员拿到的是 None——邀请码由后端控制可见性，
    不能靠前端隐藏字段来实现，那样别人直接调接口就能拿到。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="家庭组 ID")
    name: str = Field(..., description="家庭组名称")
    owner_id: int = Field(..., description="创建者用户 ID，即管理员")
    member_count: int = Field(default=0, description="成员数量")
    my_role: str = Field(..., description="我在这个家庭组里的角色：admin / member")
    invite_code: str | None = Field(
        default=None,
        description="邀请码，仅管理员可见（普通成员为 null）",
    )


class SpaceMemberInfo(BaseModel):
    """家庭组成员信息。"""

    model_config = ConfigDict(from_attributes=True)

    user_id: int = Field(..., description="用户 ID")
    nickname: str = Field(..., description="昵称")
    avatar_url: str | None = Field(default=None, description="头像地址（微信临时链接，会过期）")
    role: str = Field(..., description="角色：admin / member")
    is_owner: bool = Field(default=False, description="是否是创建者（管理员）")
