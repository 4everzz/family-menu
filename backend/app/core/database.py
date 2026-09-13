"""数据库连接：异步引擎 + 会话管理。

为什么用异步？
    FastAPI 处理请求时，如果是同步阻塞地等数据库返回，这段时间线程就被占住了。
    异步模式下等待期间可以腾出来处理其他请求，并发能力更好。

关于连接池：
    建立数据库连接是有开销的，所以 SQLAlchemy 会维护一批连接重复使用（连接池）。
    pool_pre_ping 会在取用连接前先探活，避免拿到已经被数据库关掉的旧连接。
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# 异步引擎：整个应用共用一个，内部自己管理连接池
engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_size=5,        # 常驻连接数
    max_overflow=10,    # 高峰期允许临时超出的连接数
)

# 会话工厂：每个请求创建一个会话，彼此隔离
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # 提交后对象属性仍可访问，省掉一次额外查询
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：为每个请求提供独立数据库会话，请求结束后自动关闭。

    请求过程中只要有一个环节抛异常，就回滚整个会话，
    避免"改了一半"的脏数据写进数据库。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
