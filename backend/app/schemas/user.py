"""用户相关的数据模型。"""

from pydantic import BaseModel, ConfigDict, Field


class UserInfo(BaseModel):
    """返回给前端的用户信息。

    这里刻意只暴露必要字段：
    - 密码哈希绝不出现在任何响应里，哪怕前端根本用不到；
    - is_active 这类内部状态同理，前端拿到也没用，只是多一个泄露面。

    from_attributes=True 表示可以直接把数据库对象（ORM 对象）转成这个模型，
    不用手工一个个字段去取。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="用户 ID")
    username: str | None = Field(
        default=None,
        description="登录用户名。改造前的老账号只有微信身份、没有用户名，所以可能为空",
    )
    nickname: str = Field(..., description="昵称，用户可自行修改")
    avatar_url: str | None = Field(
        default=None,
        description="头像地址。为空时前端显示默认占位头像",
    )


class UserUpdateRequest(BaseModel):
    """修改个人资料（部分更新）。

    两个字段都是可选的，只改请求体里**真正出现过**的那些：
    接口层用 model_dump(exclude_unset=True) 取出来，
    于是"没传这个字段"和"显式传 null 把它清空"能区分开——
    头像正是靠后者回到默认占位图的。

    ⚠️ nickname 声明成 `str | None` 只是为了"可以不传"，
       语义上它不能是 null（数据库那一列是 NOT NULL）。
       真传了 null 会在 Service 层被拒绝并返回一句中文提示，
       而不是在这里报 Pydantic 的错。这和 RecipeUpdateRequest 里
       category_id 的处理方式一致。
    """

    nickname: str | None = Field(
        default=None,
        max_length=20,
        description="昵称，可以填中文。不传表示不改",
    )
    avatar_url: str | None = Field(
        default=None,
        max_length=512,
        description=(
            "头像地址，用上传接口返回的相对路径（形如 /uploads/2026/09/xxx.png）。"
            "不传表示不改；传 null 表示恢复默认头像"
        ),
    )
