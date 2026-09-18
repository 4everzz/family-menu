"""拍照识别食物热量（后端化，替换根目录坏掉的 vision.js）。

⭐ 2026-09-17 重做：拆成两步，而不是让模型一口气报「这一份多少千卡」。

为什么拆？（下面都是实测数据，不是推测）
  · 让「看图那次」直接报每 100 克热量，会被图片上下文带歪：
    宫保鸡丁被报成 350 kcal/100g，而纯文字问是 180 kcal/100g（后者才在合理区间）；
    再乘上它自己估的 450g，一份算出 1440 kcal——比真实值高一倍多。
  · 拆开之后两边都稳：密度（纯文字问）4 次全一致；克重（看图估）5 次全 450g。
  → 所以：**看图只认菜名 + 克重；密度另用纯文字问；热量由我们自己相乘。**

为什么份量最终交给用户选？
  照片里判断「这一份有多少克」本身就是模糊的——这是误差的主要来源（实测密度稳定、
  克重也稳定，但克重本身可能整体偏大或偏小）。与其让模型猜，不如把决定权交给
  最清楚自己吃了多少的人。本服务给出的 `grams` 是「中份」的基准，前端按 小份/中份/大份 缩放。

配置：dashscope_api_key / dashscope_base_url / vision_model 在 config.py。
没配 key（开发/演示环境）→ 返回占位结果（mock=True），前端会提示"演示数据"。
不静默失败：网络/解析异常统一抛 BusinessError，前端按错误提示，而不是收到假 200。
"""

import asyncio
import base64
import json
import logging
import re
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
        "grams": None,
        "kcal_per_100g": None,
    },
]

# 第 1 步的提示词：刻意**只要**菜名和克重，不问热量（理由见模块 docstring）。
_RECOGNIZE_PROMPT = (
    "识别这张图片里的食物，给出菜名，以及这一份大约多少克（可食用部分的总重量）。"
    "只返回 JSON 数组，不要任何解释文字，格式："
    '[{"food_name":"菜名","grams":数字,"portion":"份量描述","confidence":0到1的数字}]'
)

# 每 100 克热量的进程内缓存。
# 一家人常做的就那几道菜，同名重复识别没必要每次都再问一遍模型；
# 密度本身是稳定值（实测同名 4 次全一致），所以缓存它是安全的。
_DENSITY_CACHE: dict[str, float] = {}
_DENSITY_CACHE_MAX = 500


def _to_float(value: object) -> float | None:
    """把模型的回复转成数字，容忍 '约 300 克' / '180 kcal' 这类带杂质的写法。"""
    if value is None:
        return None
    if isinstance(value, bool):  # bool 是 int 的子类，得先挡掉，否则 True 会被当成 1.0
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


@dataclass(frozen=True)
class FoodEstimate:
    """单条识别结果。

    calories 由 `kcal_per_100g × grams / 100` 算出，而不是模型直接给的整份热量——
    这样数字可拆开、可解释（前端会显示「450g × 180 kcal/100g」），也方便按份量缩放。
    """

    food_name: str
    calories: float
    portion: str | None = None
    confidence: float | None = None
    # 这一份的估计克重（模型看图估的）。前端拿它当「中份」基准做 小份/中份/大份 缩放。
    grams: float | None = None
    # 每 100 克多少千卡（纯文字问得，稳定）。查不到时为 None，此时 calories 为 0。
    kcal_per_100g: float | None = None


class VisionService:
    """食物热量识别。"""

    async def recognize_food(self, image_bytes: bytes) -> tuple[list[FoodEstimate], bool]:
        """返回 (识别条目, 是否占位数据)。"""
        if not settings.dashscope_api_key:
            logger.info("识别服务未配置 Key，返回占位结果（mock）")
            return [FoodEstimate(**item) for item in _MOCK_ITEMS], True

        dishes = await self._recognize_dishes(image_bytes)
        return await self._attach_density(dishes), False

    # ---------------- 第 1 步：看图 ----------------

    async def _recognize_dishes(self, image_bytes: bytes) -> list[dict]:
        body = await self._post_chat(_RECOGNIZE_PROMPT, image_bytes)
        raw = _json_array(body)

        dishes: list[dict] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            dishes.append(
                {
                    "food_name": str(item.get("food_name") or "未知食物"),
                    "grams": _to_float(item.get("grams")),
                    "portion": item.get("portion"),
                    "confidence": _to_float(item.get("confidence")),
                }
            )
        if not dishes:
            raise BusinessError("没认出食物，换个角度拍清楚点")
        return dishes

    # ---------------- 第 2 步：纯文字问密度 ----------------

    async def _density(self, dish_name: str) -> float | None:
        """问「这道菜每 100 克多少千卡」。带进程内缓存；查不到返回 None。"""
        key = dish_name.strip()
        if not key:
            return None
        cached = _DENSITY_CACHE.get(key)
        if cached is not None:
            return cached

        body = await self._post_chat(f"{key}每100克大约多少千卡？只回一个数字，不要单位、不要解释。")
        value = _to_float(_plain_text(body))
        if value is None or value <= 0:
            logger.warning("拿不到 %s 的热量密度，这一条按 0 处理", key)
            return None

        # 容量控制：满了按插入顺序丢最旧的，避免长期运行内存无限长
        while len(_DENSITY_CACHE) >= _DENSITY_CACHE_MAX:
            _DENSITY_CACHE.pop(next(iter(_DENSITY_CACHE)))
        _DENSITY_CACHE[key] = value
        return value

    async def _attach_density(self, dishes: list[dict]) -> list[FoodEstimate]:
        """并发查各道菜的密度，再算热量。

        并发不是炫技：串行的话 3 道菜要等 3 个来回，用户干等十几秒；
        并发之后总耗时 ≈ 最慢的那一次。同名的只查一次。
        """
        unique_names = list(dict.fromkeys(d["food_name"] for d in dishes))
        densities = await asyncio.gather(*(self._density(name) for name in unique_names))
        by_name = dict(zip(unique_names, densities))

        items: list[FoodEstimate] = []
        for dish in dishes:
            grams = dish["grams"]
            density = by_name.get(dish["food_name"])
            if density and grams:
                calories = round(density * grams / 100, 1)
            else:
                # 密度或克重缺了就算不出来。退一步直接问「这一份多少千卡」——
                # 那个数不如"密度×克重"稳，但**总比给用户显示 0 kcal 好**
                # （显示 0 会让人以为识别坏了）。
                calories = await self._direct_total(dish["food_name"])
            items.append(
                FoodEstimate(
                    food_name=dish["food_name"],
                    calories=calories,
                    portion=dish["portion"],
                    confidence=dish["confidence"],
                    grams=grams,
                    kcal_per_100g=density,
                )
            )
        return items

    async def _direct_total(self, dish_name: str) -> float:
        """兜底：直接问「这一份大约多少千卡」。

        正常路径走不到这里（密度和克重都在时我们自己相乘）。只在模型没回出数字、
        或看图那步没给克重时才用。查不到就返回 0——但这是最后一道防线。
        """
        try:
            body = await self._post_chat(
                f"{dish_name}一份（普通一人份）大约多少千卡？只回一个数字，不要单位、不要解释。"
            )
            value = _to_float(_plain_text(body))
        except BusinessError:
            logger.warning("%s 的兜底热量也问不到，这一条按 0 处理", dish_name)
            return 0.0
        if value is None or value <= 0:
            logger.warning("%s 的兜底热量拿不到有效数字，这一条按 0 处理", dish_name)
            return 0.0
        return value

    # ---------------- 公共请求 ----------------

    async def _post_chat(self, text: str, image_bytes: bytes | None = None) -> dict:
        """调 DashScope 的 OpenAI 兼容接口。temperature 固定 0，尽量少些随机性。"""
        content: list[dict] = []
        if image_bytes is not None:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            )
        content.append({"type": "text", "text": text})

        payload = {
            "model": settings.vision_model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.dashscope_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            logger.error("调用识别模型失败: %s", exc)
            raise BusinessError("识别服务暂时不可用，请稍后重试") from exc


def _plain_text(body: dict) -> str:
    """取出模型回复的纯文本内容。"""
    try:
        return str(body["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        raise BusinessError("识别结果格式异常")


def _json_array(body: dict) -> list:
    """从模型回复里抠出 JSON 数组。

    模型常常在 JSON 外裹一层 ```json ... ``` 或说些多余的话，
    所以不直接 json.loads 整段，而是定位第一个 '[' 和最后一个 ']' 再解析。
    """
    text = _plain_text(body).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise BusinessError("识别结果无法解析")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        raise BusinessError("识别结果无法解析")
