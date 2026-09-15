"""add dish orders

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-15 10:30:00.000000+08:00

这次加了什么（一句话）：
    新增「点单」两张表——`dish_orders`（一张单）和 `dish_order_items`（单里的明细），
    支撑"家里来客人时点单：看菜单 → 选菜 → 提交，不涉及价格和付款"。

两个外键的删除策略是刻意不同的，别顺手改成一样：
    · dish_orders.created_by → users.id 用 **RESTRICT**：
      删账号绝不能把这个人提交过的点单记录一起删掉。
    · dish_order_items.recipe_id → recipes.id 用 **SET NULL**：
      菜谱删了，那条历史点单还要留着（靠 dish_name 快照显示点了什么）。
      如果改成 RESTRICT，只要有人点过这道菜就再也删不掉菜谱；
      如果改成 CASCADE，删菜谱会把历史点单悄悄改短，记录就不可信了。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# 迁移标识（Alembic 用它串起版本链，不要手改）
revision: str = 'f6a7b8c9d0e1'
down_revision: str | None = 'e5f6a7b8c9d0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """升级：建点单主表和明细表。"""
    # ---------- 1. 点单主表 ----------
    op.create_table(
        'dish_orders',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='点单 ID'),
        sa.Column(
            'space_id',
            sa.BigInteger(),
            nullable=False,
            comment='所属家庭组。家庭组解散时，点单记录随之清理',
        ),
        sa.Column(
            'created_by',
            sa.BigInteger(),
            nullable=False,
            comment='提交者用户 ID。临时客人用创建人手机点时，这里记的就是创建人',
        ),
        sa.Column(
            'guest_name',
            sa.String(length=32),
            nullable=True,
            comment='这单是谁点的（自由填写）。客人借创建人手机点时填客人名字，家人自己点可以留空',
        ),
        sa.Column(
            'remark',
            sa.String(length=200),
            nullable=True,
            comment='整单备注，例如「少辣、不要香菜」',
        ),
        sa.Column(
            'status',
            sa.String(length=16),
            nullable=False,
            comment='点单状态：pending=待处理，done=已完成',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='创建时间',
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='更新时间',
        ),
        sa.ForeignKeyConstraint(
            ['space_id'],
            ['spaces.id'],
            name='dish_orders_space_id_fkey',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['created_by'],
            ['users.id'],
            name='dish_orders_created_by_fkey',
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dish_orders_created_by'), 'dish_orders', ['created_by'], unique=False)
    # 列表接口永远按 (space_id, status) 查，复合索引正好覆盖
    op.create_index(
        'ix_dish_orders_space_status', 'dish_orders', ['space_id', 'status'], unique=False
    )

    # ---------- 2. 点单明细表 ----------
    op.create_table(
        'dish_order_items',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column(
            'order_id',
            sa.BigInteger(),
            nullable=False,
            comment='所属点单。点单删掉时明细一起删',
        ),
        sa.Column(
            'recipe_id',
            sa.BigInteger(),
            nullable=True,
            comment='对应的菜谱 ID。菜谱被删后置空，展示一律用 dish_name',
        ),
        sa.Column(
            'dish_name',
            sa.String(length=64),
            nullable=False,
            comment='下单那一刻的菜名快照。菜谱之后改名或删除都不影响这条记录',
        ),
        sa.Column('quantity', sa.Integer(), nullable=False, comment='份数，至少 1 份'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='创建时间',
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='更新时间',
        ),
        sa.ForeignKeyConstraint(
            ['order_id'],
            ['dish_orders.id'],
            name='dish_order_items_order_id_fkey',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['recipe_id'],
            ['recipes.id'],
            name='dish_order_items_recipe_id_fkey',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_dish_order_items_order_id'), 'dish_order_items', ['order_id'], unique=False
    )


def downgrade() -> None:
    """回滚：删掉两张点单表。

    明细先删（它引用了主表）；两张表都是本次新增的，回滚不会影响任何既有数据。
    """
    op.drop_index(op.f('ix_dish_order_items_order_id'), table_name='dish_order_items')
    op.drop_table('dish_order_items')

    op.drop_index('ix_dish_orders_space_status', table_name='dish_orders')
    op.drop_index(op.f('ix_dish_orders_created_by'), table_name='dish_orders')
    op.drop_table('dish_orders')
