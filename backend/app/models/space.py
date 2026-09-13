"""家庭组（空间）相关表。

产品定位说明：
    这是一个"个人生活工作台"，菜单只是它的第一个模块。
    家庭组是"共享数据"的归属单位：菜单、购物车、冰箱这些家里人都能看到的数据，
    将来都会带一个 space_id；而饮食热量、体重这类私人数据挂在 user_id 上，两者刻意分开。

为什么用户和家庭组之间要用中间表（多对多）？
    因为一个人可以创建多个家庭组，也可以加入多个家庭组。
    如果直接在 users 表上加一个 space_id 字段，就变成"一个人只能属于一个组"，
    将来想支持多个组时必须动整个数据模型，代价很大。

谁是管理员？
    创建这个家庭组的人（spaces.owner_id），同时在成员表里记 role='admin'。
    业务上不区分"谁做菜、谁买菜"这类分工——谁在组里谁就能点菜、谁都能做菜；
    管理员身份只用来处理"把人移出家庭组"这类管理动作。
"""

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# 成员角色取值（用字符串而不是枚举，将来加角色不用改数据库结构）
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"


class Space(Base, TimestampMixin):
    """家庭组。"""

    __tablename__ = "spaces"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="家庭组 ID",
    )
    name: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="家庭组名称，允许重名（不同家庭叫同一个名字是正常的）",
    )
    owner_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="创建者用户 ID，即该家庭组的管理员",
    )
    invite_code: Mapped[str] = mapped_column(
        String(16),
        unique=True,
        index=True,
        nullable=False,
        comment="邀请码，家人凭它加入家庭组",
    )

    def __repr__(self) -> str:
        """调试时打印对象能看到关键信息，而不是一串内存地址。"""
        return f"<Space id={self.id} name={self.name!r}>"


class SpaceMember(Base, TimestampMixin):
    """家庭组成员（用户与家庭组的多对多中间表）。"""

    __tablename__ = "space_members"
    __table_args__ = (
        # 同一个用户不能重复加入同一个家庭组：靠数据库唯一约束兜底，
        # 比在代码里"先查再插"更可靠（并发下也不会插进两条）。
        UniqueConstraint("space_id", "user_id", name="uq_space_members_space_user"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键",
    )
    space_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="家庭组 ID，删组时成员记录随之清理",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="用户 ID",
    )
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ROLE_MEMBER,
        comment="成员角色：admin 管理员（创建者）/ member 普通成员",
    )

    def __repr__(self) -> str:
        """调试用。"""
        return f"<SpaceMember space={self.space_id} user={self.user_id} role={self.role}>"
