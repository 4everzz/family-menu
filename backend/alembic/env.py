"""Alembic 迁移运行时配置。

两个容易踩坑的点，这里说明白：

1) 迁移用"同步"连接，应用用"异步"连接。
   应用运行时用 async/await（并发更好），但迁移是一次性动作，用同步更简单稳定。
   本项目用的是 psycopg 3 驱动，同一份连接串（postgresql+psycopg://）
   既能用于 create_engine（同步），也能用于 create_async_engine（异步），
   所以这里直接复用 .env 里的 DATABASE_URL，不需要额外拼一份。

2) 必须把所有模型都 import 进来。
   Alembic 靠"模型元数据"和"数据库实际结构"对比来生成迁移。
   如果某个模型文件没被导入，它就不知道有这张表，生成的迁移会漏表。
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---- 让 Alembic 能 import 到 app 包（本文件位于 backend/alembic/env.py，向上两层即 backend/）----
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.models.base import Base  # noqa: E402

# 关键：导入所有模型，让它们注册到 Base.metadata 上。
# 新增模型文件后，记得在这里补一行导入，否则迁移会漏表。
from app.models import space, user  # noqa: E402,F401

# Alembic 自带的日志配置（读取 alembic.ini 里的 [loggers] 段）
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标元数据：Alembic 据此对比并生成迁移
target_metadata = Base.metadata


def get_url() -> str:
    """从应用配置读取数据库地址，避免在 alembic.ini 里写明文密码。"""
    return settings.database_url


def run_migrations_offline() -> None:
    """离线模式：不连数据库，只把 SQL 打印出来（用于人工审查或交给 DBA 执行）。"""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,           # 检测字段类型变更
        compare_server_default=True,  # 检测默认值变更
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连上数据库并真正执行迁移（日常使用这一种）。"""
    configuration = config.get_section(config.config_ini_section) or {}
    # 用代码里的连接串覆盖配置文件中的留空值
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # 迁移是一次性动作，不需要连接池
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
