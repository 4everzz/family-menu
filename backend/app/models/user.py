"""用户表。

一个微信用户对应一行。这份表是"个人私有数据域"的根：
将来饮食热量、体重、锻炼记录都挂在 user_id 上，默认不对家庭组其他成员可见。
而菜单、购物车这类家庭共享数据挂在 space_id 上，两者刻意分开。
"""

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """用户。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="用户 ID",
    )
    openid: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="微信 openid，同一小程序内唯一，登录时按它查找或创建用户",
    )
    unionid: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="微信 unionid，仅在绑定了微信开放平台账号时才有，用于跨应用识别同一用户",
    )
    nickname: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="微信用户",
        comment="昵称",
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="头像地址。注意：微信给的链接是临时地址会过期，不可长期依赖",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="是否可用，停用后无法登录",
    )

    def __repr__(self) -> str:
        """调试时打印对象能看到关键信息，而不是一串内存地址。"""
        return f"<User id={self.id} nickname={self.nickname!r}>"
