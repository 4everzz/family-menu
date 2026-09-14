"""add favorites (partitions + recipe favorites)

Revision ID: c3d4e5f6a7b8
Revises: be6f95a2c918
Create Date: 2026-09-14 18:20:00.000000+08:00

手写迁移的原因（与 be6f95a2c918 相同）：
    autogenerate 只比对结构，它不会给外键起名字、也不会按业务需要搬数据。
    这次的表全是新建的、没有存量数据要搬，
    但外键仍然**显式命名**——否则 downgrade 时的 drop_constraint(None) 会直接失败。

设计要点：
    favorite.partition_id 可空，NULL 即「默认收藏夹」。
    默认收藏夹不落库（不是一行数据，是一个状态），所以没有"首次收藏自动建行"这一步，
    也就没有存量数据要搬。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# 迁移标识（Alembic 用它串起版本链，不要手改）
revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'be6f95a2c918'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """升级：新增 favorite_partitions 与 recipe_favorites 两张表。"""
    # 1) 分区表。只有自定义分区落库；默认收藏夹是 NULL 状态，不在这里
    op.create_table(
        'favorite_partitions',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='分区 ID'),
        sa.Column('user_id', sa.BigInteger(), nullable=False,
                  comment='所属用户。分区是纯私有的，用户注销时随之清理'),
        sa.Column('name', sa.String(length=16), nullable=False,
                  comment="分区名，例如「想吃」「孩子爱吃」，同一用户内不可重名"),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0',
                  comment='显示顺序，数字小的在前。新建的排在最后'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False, comment='更新时间'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'],
                                name='fk_favorite_partitions_user_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_favorite_partitions'),
        sa.UniqueConstraint('user_id', 'name', name='uq_favorite_partitions_user_name'),
    )
    op.create_index('ix_favorite_partitions_user_sort', 'favorite_partitions',
                    ['user_id', 'sort_order'], unique=False)

    # 2) 收藏表。partition_id 为 NULL 即默认收藏夹
    op.create_table(
        'recipe_favorites',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='收藏记录 ID'),
        sa.Column('user_id', sa.BigInteger(), nullable=False,
                  comment='谁收藏的。私有域：只跟着 user_id 走'),
        sa.Column('recipe_id', sa.BigInteger(), nullable=False,
                  comment='被收藏的菜谱。菜谱没了（如家庭组解散），收藏随之消失'),
        sa.Column('partition_id', sa.BigInteger(), nullable=True,
                  comment='所在分区。NULL = 默认收藏夹（它不是一行数据，是一个状态）'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False, comment='更新时间'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'],
                                name='fk_recipe_favorites_user_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'],
                                name='fk_recipe_favorites_recipe_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['partition_id'], ['favorite_partitions.id'],
                                name='fk_recipe_favorites_partition_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_recipe_favorites'),
        sa.UniqueConstraint('user_id', 'recipe_id', name='uq_recipe_favorites_user_recipe'),
    )
    op.create_index('ix_recipe_favorites_user_partition', 'recipe_favorites',
                    ['user_id', 'partition_id'], unique=False)


def downgrade() -> None:
    """回滚：两张表整体删除。先删引用方，再删被引用方。"""
    op.drop_index('ix_recipe_favorites_user_partition', table_name='recipe_favorites')
    op.drop_table('recipe_favorites')
    op.drop_index('ix_favorite_partitions_user_sort', table_name='favorite_partitions')
    op.drop_table('favorite_partitions')
