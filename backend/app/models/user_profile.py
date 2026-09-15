"""个人健康档案（私有域：挂在 user_id 上）。

健康数据属于个人，不应该对家庭组其他成员可见——和菜谱/冰箱（space_id 共享）是两条线。
users.py 的模块注释已经预留了这个位置："将来饮食热量、体重、锻炼记录都挂在 user_id 上"。

两张表：
  · user_profiles  一人一行的基本档案（性别/身高/体重/目标/饮食备注）
  · calorie_logs   拍照/手动记录的热量，可按天汇总
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# 性别可选值
GENDER_MALE = "male"
GENDER_FEMALE = "female"
GENDER_OTHER = "other"

# 目标可选值
GOAL_LOSE = "lose"          # 减脂
GOAL_MAINTAIN = "maintain"  # 维持
GOAL_GAIN = "gain"          # 增肌

# 饮食备注最大长度（自由文本）
MAX_DIET_PREFERENCES_LENGTH = 500


class UserProfile(Base, TimestampMixin):
    """个人健康档案：每个用户最多一行。"""

    __tablename__ = "user_profiles"
    __table_args__ = (
        # 一人一行：不让同一个用户出现两份档案
        UniqueConstraint("user_id", name="uq_user_profiles_user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="档案 ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属用户。私有域：用户注销时一并清理",
    )
    gender: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="性别：male / female / other"
    )
    height_cm: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 1), nullable=True, comment="身高（厘米）"
    )
    weight_kg: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 1), nullable=True, comment="体重（千克）"
    )
    goal: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment="目标：lose 减脂 / maintain 维持 / gain 增肌",
    )
    diet_preferences: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="饮食备注：自由文本，如「减脂期·清淡饮食·忌辛辣」",
    )


class CalorieLog(Base, TimestampMixin):
    """一条热量记录：拍照识别或手动添加，可挂在某天、可看历史。"""

    __tablename__ = "calorie_logs"
    __table_args__ = (
        # 按天查历史/汇总，复合索引正好覆盖
        Index("ix_calorie_logs_user_eaten", "user_id", "eaten_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="记录 ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="谁记的。私有域",
    )
    eaten_at: Mapped[date] = mapped_column(
        Date, nullable=False, comment="食用日期（按天汇总用）"
    )
    food_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="食物名称")
    calories: Mapped[Decimal] = mapped_column(
        Numeric(8, 1), nullable=False, comment="估算热量（kcal）"
    )
    portion: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="份量描述，如「一碗」「约 200g」"
    )
    image_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="识别用图的相对路径，可为空（手动添加）"
    )
    source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="vision",
        comment="来源：vision 拍照识别 / manual 手动添加",
    )
