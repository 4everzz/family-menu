"""v1 版本路由汇总。

每个功能模块一个路由文件，统一在这里挂载。
新增模块（家庭组、菜单、冰箱等）时只需在这里加一行。
"""

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    categories,
    favorites,
    fridge,
    health,
    recipes,
    spaces,
    uploads,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(spaces.router)
# 分类路由要挂在菜谱路由之前吗？不必要——两者的路径前缀不同
# （/spaces/{id}/categories 与 /spaces/{id}/recipes），不会互相遮挡。
api_router.include_router(categories.router)
api_router.include_router(recipes.router)
# 收藏路由内部有 /favorites/partitions 与 /favorites/{recipe_id} 的顺序问题，
# 在 favorites.py 里已经把静态路径写在前面了，这里照常挂载即可。
api_router.include_router(favorites.router)
# 冰箱路由：家庭共享域，挂在 space_id 下（/spaces/{id}/fridge）
api_router.include_router(fridge.router)
# 上传接口：multipart 表单，前端用 uni.uploadFile 调用
api_router.include_router(uploads.router)
