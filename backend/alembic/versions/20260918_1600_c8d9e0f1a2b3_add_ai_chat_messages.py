"""add ai_chat_messages

Revision ID: c8d9e0f1a2b3
Revises: b1c2d3e4f5a6
Create Date: 2026-09-18 16:00:00.000000+08:00

手写迁移的原因（与前面的迁移一致）：
    autogenerate 只比对结构，不会给外键起名字。
    外键必须**显式命名**——否则 downgrade 时的 drop_constraint(None) 会直接失败。

设计要点：
    AI 对话历史挂在 user_id 上的私有域，随用户注销 CASCADE 清理；
    唯一的高频查询是"取某用户最近 N 条"，(user_id, created_at) 复合索引正好覆盖。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# 迁移标识（Alembic 用它串起版本链，不要手改）
revision: str = 'c8d9e0f1a2b3'
down_revision: str | None = 'b1c2d3e4f5a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """升级：新增 ai_chat_messages 表。"""
    op.create_table(
        'ai_chat_messages',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='消息 ID'),
        sa.Column('user_id', sa.BigInteger(), nullable=False,
                  comment='谁的对话。私有域：用户注销时一并清理'),
        sa.Column('role', sa.String(length=16), nullable=False,
                  comment='角色：user 用户 / assistant AI'),
        sa.Column('content', sa.Text(), nullable=False, comment='消息文本'),
        sa.Column('actions', sa.JSON(), nullable=True,
                  comment='assistant 消息附带的动作草案（原样存，仅备查；user 消息为 null）'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False, comment='更新时间'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'],
                                name='fk_ai_chat_messages_user_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_ai_chat_messages'),
    )
    op.create_index('ix_ai_chat_messages_user_created', 'ai_chat_messages',
                    ['user_id', 'created_at'], unique=False)


def downgrade() -> None:
    """回滚：整表删除。"""
    op.drop_index('ix_ai_chat_messages_user_created', table_name='ai_chat_messages')
    op.drop_table('ai_chat_messages')
