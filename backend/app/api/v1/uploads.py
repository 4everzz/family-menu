"""图片上传接口。

权限：登录即可上传。上传本身只产生一个文件，不产生任何业务数据；
真正的权限控制在"把 image_url 挂到哪道菜上"——那走菜谱的创建人校验。
"""

from fastapi import APIRouter, UploadFile

from app.api.deps import CurrentUser
from app.core.response import success
from app.services.upload_service import UploadService

router = APIRouter(tags=["上传"])


@router.post("/uploads/image", summary="上传一张菜品图片")
async def upload_image(file: UploadFile, current_user: CurrentUser) -> dict:
    """上传图片，返回可直接存进 recipes.image_url 的**相对路径**。

    只存相对路径（如 /uploads/2026/09/xxx.png）是刻意为之：
    前端拼上自己的 base 地址再显示，将来打包 App 换域名时数据不用动。
    """
    content = await file.read()
    service = UploadService()
    return success(await service.save_image(file.filename or "", content))
