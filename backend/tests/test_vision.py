"""临时食物照片识别接口测试。"""

from pathlib import Path

from httpx import AsyncClient

from app.core.config import settings
from app.services.vision_service import FoodEstimate

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"test-image"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_temporary_vision_does_not_write_uploaded_image(
    client: AsyncClient, login_as, tmp_path: Path, monkeypatch
) -> None:
    """识别使用上传内容本身，不在永久图片目录创建文件。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    async def fake_recognize(self, image_bytes: bytes):
        assert image_bytes == PNG_BYTES
        return [FoodEstimate(food_name="米饭", calories=130, grams=100)], False

    monkeypatch.setattr("app.api.v1.vision.VisionService.recognize_food", fake_recognize)
    token, _ = await login_as("vision-temp")

    response = await client.post(
        "/api/v1/vision/recognize-food/image",
        files={"file": ("meal.png", PNG_BYTES, "image/png")},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"][0]["food_name"] == "米饭"
    assert list(tmp_path.rglob("*")) == []


async def test_temporary_vision_rejects_invalid_image(client: AsyncClient, login_as) -> None:
    token, _ = await login_as("vision-invalid")
    response = await client.post(
        "/api/v1/vision/recognize-food/image",
        files={"file": ("not-image.png", b"not an image", "image/png")},
        headers=_auth(token),
    )
    assert response.status_code == 400, response.text
    assert "不是有效的图片" in response.json()["message"]


async def test_temporary_vision_requires_login(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/vision/recognize-food/image",
        files={"file": ("meal.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 401, response.text
