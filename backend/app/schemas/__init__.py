"""请求与响应的数据模型（Pydantic）。

作用：定义接口的"契约"。
    - 进来的请求参数会被校验，不合规直接返回 422，不用在业务代码里手写一堆 if；
    - 出去的响应会按定义裁剪字段，避免把不该给前端的数据（比如内部标记）带出去。
"""

from app.schemas.auth import (
    LoginResponse,
    PasswordLoginRequest,
    RegisterRequest,
    WechatLoginRequest,
)
from app.schemas.category import CategoryCreateRequest, CategoryInfo, CategoryUpdateRequest
from app.schemas.recipe import RecipeCreateRequest, RecipeInfo, RecipeUpdateRequest
from app.schemas.space import SpaceCreateRequest, SpaceInfo, SpaceJoinRequest, SpaceMemberInfo
from app.schemas.user import UserInfo, UserUpdateRequest

__all__ = [
    "RegisterRequest",
    "PasswordLoginRequest",
    "WechatLoginRequest",
    "LoginResponse",
    "UserInfo",
    "UserUpdateRequest",
    "SpaceCreateRequest",
    "SpaceJoinRequest",
    "SpaceInfo",
    "SpaceMemberInfo",
    "CategoryCreateRequest",
    "CategoryUpdateRequest",
    "CategoryInfo",
    "RecipeCreateRequest",
    "RecipeUpdateRequest",
    "RecipeInfo",
]
