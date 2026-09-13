"""应用入口：创建 FastAPI 实例、注册中间件与路由。

分层总览（请求自上而下穿过各层）：
    路由层(api) → 业务层(services) → 数据访问层(repositories) → 数据库
    业务层需要额外能力时，再去调外部服务（如微信接口）。

这样分层的好处：路由只关心参数与返回，规则集中在业务层，
数据库操作集中在数据访问层，任何一层要改都不会牵动其他层。
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import register_exception_handlers

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动与关闭时的动作。

    启动时打印环境信息；关闭时释放数据库连接池，
    避免服务重启过程中残留连接把数据库连接数占满。
    """
    logger.info("服务启动 | 环境=%s | 接口前缀=%s", settings.app_env, settings.api_prefix)

    if settings.auth_dev_mode:
        # 用醒目格式提醒，防止误把开发模式带上生产
        logger.warning("=" * 64)
        logger.warning("⚠️  AUTH_DEV_MODE 已开启：登录不校验微信，仅供本地联调！")
        logger.warning("=" * 64)

    yield

    await engine.dispose()
    logger.info("服务已关闭，数据库连接池已释放")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="小家智膳后端：家庭菜单与个人生活工作台",
        lifespan=lifespan,
        # 生产环境关闭在线接口文档，避免把接口细节对外暴露
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_prod else "/openapi.json",
    )

    # 跨域配置：小程序不受浏览器同源策略限制，这里主要为将来的 H5 端与本地调试预留
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[] if settings.is_prod else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 全局异常处理：统一把错误转成 { code, message, data }
    register_exception_handlers(app)

    # 挂载业务路由
    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
