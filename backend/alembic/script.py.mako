"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

# 迁移标识（Alembic 用它串起版本链，不要手改）
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """升级：把数据库结构改到本版本的样子。"""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """回滚：把本版本的改动撤销掉。"""
    ${downgrades if downgrades else "pass"}
