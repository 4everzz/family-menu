"""拍照识别食物热量。

前端流程：chooseImage → uploadImage（拿到相对路径 /uploads/...）→ 调本接口识别。
后端按相对路径读回图片字节，交给 VisionService（没配 Key 时返回占位结果）。
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.core.response import success
from app.schemas.user_profile import FoodEstimate as FoodEstimateSchema, RecognizeFoodResponse
from app.services.upload_service import UploadService
from app.services.vision_service import FoodEstimate, VisionService

router = APIRouter(tags=["识别"])


class RecognizeFoodRequest(BaseModel):
    """前端传上传接口返回的相对路径即可。"""

    image_url: str = Field(..., description="上传接口返回的相对路径，如 /uploads/2026/09/xxx.png")


@router.post("/vision/recognize-food", summary="拍照识别食物热量")
async def recognize_food(
    payload: RecognizeFoodRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """读回图片字节 → 调识别服务 → 返回结构化结果。需要登录。"""
    image_bytes = UploadService().read_upload_bytes(payload.image_url)
    items, mock = await VisionService().recognize_food(image_bytes)
    response = RecognizeFoodResponse(
        items=[
            FoodEstimateSchema(
                food_name=i.food_name,
                calories=i.calories,
                portion=i.portion,
                confidence=i.confidence,
            )
            for i in items
        ],
        mock=mock,
    )
    return success(response.model_dump())
