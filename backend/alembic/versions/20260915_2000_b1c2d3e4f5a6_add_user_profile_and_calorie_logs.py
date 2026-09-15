"""add user_profile + calorie_logs

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-09-15 20:00:00.000000+08:00

手写迁移的原因（与前面的迁移一致）：
    autogenerate 只比对结构，不会给外键起名字。
    外键必须**显式命名**——否则 downgrade 时的 drop_constraint(None) 会直接失败。

设计要点：
    user_profiles 一人一行（user_id 唯一），随用户注销 CASCADE 清理；
    calorie_logs 挂在 user_id 上的私有记录，按 (user_id, eaten_at) 建索引方便按天汇总。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# 迁移标识（Alembic 用它串起版本链，不要手改）
revision: str = 'b1c2d3e4f5a6'
down_revision: str | None = 'a7b8c9d0e1f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """升级：新增 user_profiles 与 calorie_logs 两张表。"""
    op.create_table(
        'user_profiles',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='档案 ID'),
        sa.Column('user_id', sa.BigInteger(), nullable=False,
                  comment='所属用户。私有域：用户注销时一并清理'),
        sa.Column('gender', sa.String(length=8), nullable=True,
                  comment='性别：male / female / other'),
        sa.Column('height_cm', sa.Numeric(precision=5, scale=1), nullable=True,
                  comment='身高（厘米）'),
        sa.Column('weight_kg', sa.Numeric(precision=5, scale=1), nullable=True,
                  comment='体重（千克）'),
        sa.Column('goal', sa.String(length=16), nullable=True,
                  comment='目标：lose 减脂 / maintain 维持 / gain 增肌'),
        sa.Column('diet_preferences', sa.Text(), nullable=True,
                  comment='饮食备注：自由文本，如「减脂期·清淡饮食·忌辛辣」'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False, comment='更新时间'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'],
                                name='fk_user_profiles_user_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_user_profiles'),
        sa.UniqueConstraint('user_id', name='uq_user_profiles_user_id'),
    )

    op.create_table(
        'calorie_logs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='记录 ID'),
        sa.Column('user_id', sa.BigInteger(), nullable=False,
                  comment='谁记的。私有域'),
        sa.Column('eaten_at', sa.Date(), nullable=False, comment='食用日期（按天汇总用）'),
        sa.Column('food_name', sa.String(length=128), nullable=False, comment='食物名称'),
        sa.Column('calories', sa.Numeric(precision=8, scale=1), nullable=False,
                  comment='估算热量（kcal）'),
        sa.Column('portion', sa.String(length=64), nullable=True,
                  comment='份量描述，如「一碗」「约 200g」'),
        sa.Column('image_url', sa.String(length=512), nullable=True,
                  comment='识别用图的相对路径，可为空（手动添加）'),
        sa.Column('source', sa.String(length=16), nullable=False, server_default='vision',
                  comment='来源：vision 拍照识别 / manual 手动添加'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False, comment='更新时间'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'],
                                name='fk_calorie_logs_user_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_calorie_logs'),
    )
    op.create_index('ix_calorie_logs_user_eaten', 'calorie_logs',
                    ['user_id', 'eaten_at'], unique=False)


def downgrade() -> None:
    """回滚：两张表整体删除。"""
    op.drop_index('ix_calorie_logs_user_eaten', table_name='calorie_logs')
    op.drop_table('calorie_logs')
    op.drop_table('user_profiles')
