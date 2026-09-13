"""系统类接口：健康检查。"""

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import settings
from app.core.response import success

router = APIRouter(tags=["系统"])


@router.get("/health", summary="健康检查")
async def health(session: DbSession) -> dict:
    """探活接口。

    除了说明服务活着，还顺手执行一条最简单的 SQL 验证数据库连通性——
    不然服务进程在、数据库断了，健康检查却返回正常，会误导排查方向。
    """
    await session.execute(text("SELECT 1"))
    return success(
        {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
            "database": "connected",
            "auth_dev_mode": settings.auth_dev_mode,
        }
    )
