"""add fridge_items

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-14 21:00:00.000000+08:00

手写迁移的原因（与之前一致）：
    autogenerate 只比对结构，不会给外键起名字、也不会按业务需要搬数据。
    这张表是新建的、没有存量数据要搬，但外键仍然**显式命名**——
    否则 downgrade 时的 drop_constraint(None) 会直接失败。

设计要点：
    fridge_items 是家庭共享域，space_id 跟随家庭组级联删除（CASCADE）；
    created_by 用 RESTRICT——删用户账号不能把他家冰箱库存一起删掉。
    数量用 Float（家庭库存精度足够，且避免 Decimal/JSON 序列化问题）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# 迁移标识（Alembic 用它串起版本链，不要手改）
revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = 'c3d4e5f6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """升级：新增 fridge_items 表。"""
    op.create_table(
        'fridge_items',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='食材 ID'),
        sa.Column('space_id', sa.BigInteger(), nullable=False,
                  comment='所属家庭组。家庭组解散时，冰箱食材随之清理'),
        sa.Column('name', sa.String(length=64), nullable=False, comment='食材名，例如「鸡蛋」'),
        sa.Column('quantity', sa.Float(), nullable=False, comment='数量'),
        sa.Column('unit', sa.String(length=8), nullable=True, comment='单位，例如「个」「克」「盒」'),
        sa.Column('category', sa.String(length=16), nullable=True,
                  comment='分类：蔬菜/肉蛋/水产/调料/饮品/其他'),
        sa.Column('storage', sa.String(length=8), nullable=True,
                  comment='存放位置：冷藏/冷冻/常温'),
        sa.Column('expiry_date', sa.Date(), nullable=True, comment='保质期（日期）'),
        sa.Column('note', sa.String(length=200), nullable=True, comment='备注'),
        sa.Column('created_by', sa.BigInteger(), nullable=False,
                  comment='添加者用户 ID，仅用于展示「谁加的」'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False, comment='更新时间'),
        sa.ForeignKeyConstraint(['space_id'], ['spaces.id'],
                                name='fk_fridge_items_space_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'],
                                name='fk_fridge_items_created_by', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name='pk_fridge_items'),
    )
    op.create_index('ix_fridge_items_space_id', 'fridge_items', ['space_id'], unique=False)


def downgrade() -> None:
    """回滚：删表（先删引用方，再删被引用方）。"""
    op.drop_index('ix_fridge_items_space_id', table_name='fridge_items')
    op.drop_table('fridge_items')
