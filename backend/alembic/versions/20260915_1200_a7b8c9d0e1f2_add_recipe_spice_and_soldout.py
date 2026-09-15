"""add recipe spice options and sold-out flag

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-15 12:00:00.000000+08:00

这次加了什么（一句话）：
    把旧小程序版里的「**辣度设置**」和「**售罄**」搬到新后端：
    · recipes 加 `spice_options` / `default_spice` / `is_sold_out`；
    · dish_order_items 加 `spice`（下单时的辣度快照）。

为什么辣度存成 JSON 数组而不是另开一张表：
    一道菜的辣度档位就固定那四档（不辣/微辣/正常辣/特辣），
    既不需要单独查询、也不需要外键约束，开一张 `recipe_spices` 表属于过度设计——
    多一张表就多一处 join、多一处要维护的一致性。
    存成 JSON 数组，读写都是"整取整存"，和实际用法完全吻合。

`is_sold_out` 不是商家的"库存"：
    家里做饭没有"卖完了"这回事，但有"今天不想做/食材没了"。
    所以它是一个**临时开关**，随时可以取消，也不参与任何库存计算。
    和旧小程序版的 `enabled`/`dailyStock`/`stock` 那套刻意不同——那些是开店才需要的。

新增列都给了 server_default，所以对存量数据是安全的：
    · spice_options 默认 `[]`（不问辣度）
    · is_sold_out 默认 false（照常能做）
    · dish_order_items.spice 可空（老数据没有辣度，显示时跳过这一行即可）
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# 迁移标识（Alembic 用它串起版本链，不要手改）
revision: str = 'a7b8c9d0e1f2'
down_revision: str | None = 'f6a7b8c9d0e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """升级：给菜谱加辣度与售罄，给点单明细加辣度快照。"""
    op.add_column(
        'recipes',
        sa.Column(
            'spice_options',
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
            comment=(
                '这道菜支持哪几档辣度，取值只能是 SPICE_LEVELS 里的，顺序按 SPICE_LEVELS 归一化。'
                '空数组表示点这道菜时不问辣度（比如汤、饮品）'
            ),
        ),
    )
    op.add_column(
        'recipes',
        sa.Column(
            'default_spice',
            sa.String(length=16),
            nullable=True,
            comment='默认辣度，必须是 spice_options 里的一个。为空时取第一档',
        ),
    )
    op.add_column(
        'recipes',
        sa.Column(
            'is_sold_out',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
            comment=(
                '「今天不做」：临时标记，比如买了菜回来发现少了食材。'
                '和商家的「库存」不是一回事——这里只是今天先不做这道，随时可以取消'
            ),
        ),
    )
    op.add_column(
        'dish_order_items',
        sa.Column(
            'spice',
            sa.String(length=16),
            nullable=True,
            comment=(
                '下单时选的辣度快照。和 dish_name 是同一个道理——'
                '菜单以后改了辣度档位，这张历史单依然说得清当时要的是什么口味'
            ),
        ),
    )


def downgrade() -> None:
    """回滚：把这次加的四列删掉。

    四列都是新增且可空（或带默认值），回滚不会影响任何既有数据。
    删掉之后辣度和售罄信息就没了——那是预期的，因为它们本来就本该由这次迁移提供。
    """
    op.drop_column('dish_order_items', 'spice')
    op.drop_column('recipes', 'is_sold_out')
    op.drop_column('recipes', 'default_spice')
    op.drop_column('recipes', 'spice_options')
