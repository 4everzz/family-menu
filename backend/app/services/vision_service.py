"""拍照识别食物热量（后端化，替换根目录坏掉的 vision.js）。

设计：
  · 优先走真实模型：DashScope 的 Qwen-VL（OpenAI 兼容 /chat/completions）。
    配置项 dashscope_api_key / dashscope_base_url / vision_model 在 config.py。
  · 没配 key（开发/演示环境）→ 返回占位结果（mock=True），前端会提示"演示数据"，
    保证整条交互链路可跑、可验收；用户把可用 Key 写进 backend/.env 即自动接通真实模型。
  · 不静默失败：网络/解析异常统一抛 BusinessError，前端按错误提示，而不是收到假 200。

⚠️ vision_model 的默认值只是占位：实现时请核对 DashScope 当前在售的 VL 模型 id
（如 qwen-vl-max / qwen2.5-vl-72b-instruct），它做成可配就是为了随时调整。
"""

import base64
import json
import logging
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.exceptions import BusinessError

logger = logging.getLogger(__name__)

# 占位识别结果（无 key 时返回，让 UI 流程可测）
_MOCK_ITEMS = [
    {
        "food_name": "示例菜品（演示数据）",
        "calories": 0.0,
        "portion": "未配置识别 Key",
        "confidence": 0.0,
    },
]


@dataclass(frozen=True)
class FoodEstimate:
    """单条识别结果。"""

    food_name: str
    calories: float
    portion: str | None = None
    confidence: float | None = None


class VisionService:
    """食物热量识别。"""

    async def recognize_food(self, image_bytes: bytes) -> tuple[list[FoodEstimate], bool]:
        """返回 (识别条目, 是否占位数据)。"""
        if not settings.dashscope_api_key:
            logger.info("识别服务未配置 Key，返回占位结果（mock）")
            return [FoodEstimate(**item) for item in _MOCK_ITEMS], True

        items = await self._call_qwen_vl(image_bytes)
        return items, False

    async def _call_qwen_vl(self, image_bytes: bytes) -> list[FoodEstimate]:
        """调用 Qwen-VL，把图片和提示词发过去，解析出食物热量列表。"""
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_uri = f"data:image/jpeg;base64,{b64}"
        prompt = (
            "请识别这张图片里的食物，估算每份的热量（kcal）。"
            "只返回 JSON 数组，不要任何解释文字，格式："
            '[{"food_name":"菜名","calories":数字,"portion":"份量描述","confidence":0到1的数字}]'
        )
        payload = {
            "model": settings.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_uri}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{settings.dashscope_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                body = resp.json()
        except httpx.HTTPError as exc:
            logger.error("调用识别模型失败: %s", exc)
            raise BusinessError("识别服务暂时不可用，请稍后重试") from exc

        return self._parse_items(body)

    @staticmethod
    def _parse_items(body: dict) -> list[FoodEstimate]:
        """从模型返回里抠出 JSON 数组，转成 FoodEstimate 列表。"""
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise BusinessError("识别结果格式异常")
        # 模型可能在 JSON 外裹了 ```json ... ``` 或说了多余的话，尽量抠出数组
        text = content.strip()
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            raise BusinessError("识别结果无法解析")
        try:
            raw = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            raise BusinessError("识别结果无法解析")

        items: list[FoodEstimate] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("food_name") or "未知食物")
            try:
                cal = float(item.get("calories") or 0)
            except (TypeError, ValueError):
                cal = 0.0
            portion = item.get("portion")
            try:
                conf = float(item["confidence"]) if item.get("confidence") is not None else None
            except (TypeError, ValueError):
                conf = None
            items.append(
                FoodEstimate(food_name=name, calories=cal, portion=portion, confidence=conf)
            )
        if not items:
            raise BusinessError("没认出食物，换个角度拍清楚点")
        return items
