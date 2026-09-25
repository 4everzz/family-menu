"""scope ai chat history by space

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-09-24 10:00:00.000000+08:00

旧聊天记录的 space_id 保持为空，作为个人聊天历史。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """增加家庭归属字段，旧记录保留为个人聊天。"""
    op.add_column(
        "ai_chat_messages",
        sa.Column("space_id", sa.BigInteger(), nullable=True, comment="所属家庭；为空表示个人聊天，旧记录保留为空"),
    )
    op.create_foreign_key(
        "fk_ai_chat_messages_space_id",
        "ai_chat_messages",
        "spaces",
        ["space_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("ix_ai_chat_messages_user_created", table_name="ai_chat_messages")
    op.create_index(
        "ix_ai_chat_messages_user_space_created",
        "ai_chat_messages",
        ["user_id", "space_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """恢复旧结构；新产生的家庭聊天数据会随 space_id 列一并删除。"""
    op.drop_index("ix_ai_chat_messages_user_space_created", table_name="ai_chat_messages")
    op.create_index(
        "ix_ai_chat_messages_user_created",
        "ai_chat_messages",
        ["user_id", "created_at"],
        unique=False,
    )
    op.drop_constraint(
        "fk_ai_chat_messages_space_id", "ai_chat_messages", type_="foreignkey"
    )
    op.drop_column("ai_chat_messages", "space_id")
