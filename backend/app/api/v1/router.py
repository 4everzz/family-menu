"""v1 版本路由汇总。

每个功能模块一个路由文件，统一在这里挂载。
新增模块（家庭组、菜单、冰箱等）时只需在这里加一行。
"""

from fastapi import APIRouter

from app.api.v1 import (
    ai_chat,
    alerts,
    auth,
    categories,
    favorites,
    fridge,
    health,
    orders,
    recipes,
    spaces,
    uploads,
    user_profile,
    users,
    vision,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(user_profile.router)
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
# 点单路由：家庭共享域，挂在 space_id 下（/spaces/{id}/orders）
api_router.include_router(orders.router)
# 上传接口：multipart 表单，前端用 uni.uploadFile 调用
api_router.include_router(uploads.router)
# 拍照识别食物热量：读回上传的图片字节，交给多模态模型（无 key 走占位）
api_router.include_router(vision.router)
# 家庭提醒：把冰箱"该注意的状态"聚合成列表（临期/过期 + 缺货），纯读、无新表
api_router.include_router(alerts.router)
# AI 对话：用一句话记账。**只产出待确认的草案，不写库**——
# 用户在卡片上点「记下」后，前端调已有的 /users/me/calorie-logs 写入。
api_router.include_router(ai_chat.router)
