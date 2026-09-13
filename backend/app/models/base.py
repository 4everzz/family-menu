"""SQLAlchemy 模型基类与公共字段。

关于时间字段：
    用数据库端的 now() 生成时间，而不是用 Python 的当前时间。
    因为将来可能有多个应用实例同时跑（云托管会自动扩容），
    各机器时钟可能有细微差异，交给数据库统一生成才不会乱序。
"""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有表的公共基类，统一挂在同一个 metadata 上供迁移工具扫描。"""


class TimestampMixin:
    """公共时间字段：创建时间与更新时间。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )
