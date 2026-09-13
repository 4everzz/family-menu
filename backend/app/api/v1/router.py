"""v1 版本路由汇总。

每个功能模块一个路由文件，统一在这里挂载。
新增模块（家庭组、菜单、冰箱等）时只需在这里加一行。
"""

from fastapi import APIRouter

from app.api.v1 import auth, health, spaces, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(spaces.router)
