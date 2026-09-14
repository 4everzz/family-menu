"""用户表。

一个用户对应一行。这份表是"个人私有数据域"的根：
将来饮食热量、体重、锻炼记录都挂在 user_id 上，默认不对家庭组其他成员可见。
而菜单、冰箱这类家庭共享数据挂在 space_id 上，两者刻意分开。

⚠️ 这张表只回答"这个人是谁"，不回答"这个人怎么登录"。
   "怎么登录"（微信小程序等）放在 user_identities 表里。
   混在一起的代价：每加一种登录方式就得往这张表加一列
   （openid / qq_openid / phone_openid / apple_id ...），
   而每一列对绝大多数用户都是空的，表会越来越不像一张表。
"""

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# 用户名规则。前后端共用同一套口径：
# 前端只是提前提示，真正的闸门永远在后端——前端校验是体验，不是安全。
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 20

# 新用户的默认昵称。用户可以在「我的」页自己改
DEFAULT_NICKNAME = "小家用户"


class User(Base, TimestampMixin):
    """用户。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="用户 ID",
    )
    username: Mapped[str | None] = mapped_column(
        String(32),
        unique=True,
        index=True,
        nullable=True,
        comment=(
            "登录用户名：3-20 位 ASCII 字母/数字/下划线，统一存小写（避免 Tom 和 tom 变成两个账号）。"
            "允许为空是为了兼容改造前那批只有微信 openid 的老用户——他们目前只能走小程序登录"
        ),
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="密码哈希（bcrypt）。绝不存明文；为空表示该账号尚未设置密码",
    )
    nickname: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=DEFAULT_NICKNAME,
        comment="昵称，用户可自行修改",
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="头像地址。为空时前端显示默认占位头像，而不是留一片空白",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="是否可用，停用后无法登录",
    )

    def __repr__(self) -> str:
        """调试时打印对象能看到关键信息，而不是一串内存地址。"""
        return f"<User id={self.id} username={self.username!r}>"
