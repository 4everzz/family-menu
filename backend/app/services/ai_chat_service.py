"""AI 对话（本轮落地：用一句话记账）。

职责很单一：把用户这一句（加少量历史）交给模型，拿回一个结构化 JSON —— 
「自然语言回复」+「动作草案」，然后返回给前端。

⭐ **这个服务不写库。**
   写库发生在用户点确认卡片之后，由前端调**已有的** /users/me/calorie-logs 完成。
   为什么这么切？见 schemas/ai_chat.py 的模块注释——模型只给"提议权"，
   出错了最多是卡片显示错，不会把脏数据写进用户的记录里。

HTTP 调用照抄 vision_service 的形态：httpx 直连 DashScope 的 OpenAI 兼容接口，
temperature=0（这里要的是"可解析、不随机"，不是创意），
HTTP 错误 → BusinessError（不静默失败），没配 Key → 占位 + mock=True（前端会明说是演示）。
"""

import json
import logging
import re
from datetime import date, datetime, timedelta

import httpx

from app.core.config import settings
from app.core.exceptions import BusinessError
from app.core.response import CODE_PARAM_INVALID
from app.schemas.ai_chat import ActionDraft, AiChatRequest, AiChatResponse, AiChatTurn

logger = logging.getLogger(__name__)

# 历史最多带几轮：只用来消解"再加一碗"这类省略句，带太多既费 token 又容易带偏
MAX_HISTORY_TURNS = 6
# 单条历史消息截断长度（防止把 prompt 撑爆）
MAX_HISTORY_CHARS = 300
# 热量合理区间。超出基本是听错了或多打个 0，这种值一律不采信。
MAX_REASONABLE_KCAL = 10000

# 动作类型：本轮只有"记一笔热量"
KIND_CREATE_CALORIE_LOG = "create_calorie_log"

# 没配 Key 时的占位回复。不假装成功——前端会把它连同"演示数据"提示一起展示。
_MOCK_REPLY = "AI 服务还没配置好（后端缺 DashScope Key），现在还没法帮你记账。"

_SYSTEM_PROMPT = """你是一个家庭饮食记账助手。用户会用一句大白话说他吃了什么，
你的任务是把它整理成结构化数据。**只输出一个 JSON 对象**，不要 markdown 代码块、
不要任何解释文字。JSON 结构：

{"intent":"log|chat|recommend","reply":"给用户看的一句话","actions":[
  {"kind":"create_calorie_log","food_name":"菜名","portion":"份量或null",
   "calories":数字或null,"calories_estimated":true或false,"eaten_at":"YYYY-MM-DD"}
]}

今天是 {today}。

字段规则：
- intent：用户在说"吃了/喝了什么"用 log；用户在问吃什么好、要推荐用 recommend；
  其它（闲聊、问你是谁、说了但听不懂）用 chat。
- reply：一句自然的中文，像家人说话，别啰嗦、别复述规则。log 时必须用一句话
  告诉用户你记下了什么。
- actions：只有 intent=log 时才填，且一次最多一条；其它情况必须是空数组 []。
- food_name：菜名，尽量用用户的原词。
- portion：**只有用户明确说了份量/重量才填**，照抄他的说法（如 "500g"、"两碗"）。
  用户没提就填 null —— 不要猜、不要替他编一个份量。
- calories：用户给了热量就用他的数，calories_estimated 填 false；
  用户没说热量时，你按常识估一个，calories_estimated 填 true，并在 reply 里
  明确说一句"热量是我估的，不对就改"，别让他以为是自己说的。
- eaten_at：默认填上面那个"今天"的日期。用户说"中午/晚上"**不影响**它（本系统只记到天，
  不区分餐段）；但用户明确说"昨天"就填昨天。其它任何日期一律填今天。

几个例子：

用户：中午吃了红烧肉500g，550kcal
{"intent":"log","reply":"记下了：红烧肉 500g，550 kcal。","actions":[{"kind":"create_calorie_log","food_name":"红烧肉","portion":"500g","calories":550,"calories_estimated":false,"eaten_at":"{today}"}]}

用户：刚吃了个苹果
{"intent":"log","reply":"记下了：苹果一份。热量是我按常识估的（约 90 kcal），不对就改一下。","actions":[{"kind":"create_calorie_log","food_name":"苹果","portion":null,"calories":90,"calories_estimated":true,"eaten_at":"{today}"}]}

用户：喝了碗米饭
{"intent":"log","reply":"记下了：米饭 一碗。热量是我估的（约 230 kcal），不对就改。","actions":[{"kind":"create_calorie_log","food_name":"米饭","portion":"一碗","calories":230,"calories_estimated":true,"eaten_at":"{today}"}]}

用户：今天天气不错
{"intent":"chat","reply":"是挺好的～想记点什么吃的话直接跟我说就行。","actions":[]}

用户：今晚吃什么好
{"intent":"recommend","reply":"推荐菜的功能我还在学，暂时帮不上忙。你先告诉我吃了什么，我帮你记着。","actions":[]}

用户：我吃了个那个东西
{"intent":"chat","reply":"没太听清是什么东西，能说得具体点吗？比如「红烧肉 500g」这样的。","actions":[]}
"""


def _to_float(value: object) -> float | None:
    """把模型给的值转成数字，容忍 '约550kcal' / '500 克' 这类带杂质的写法。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def _clean_text(value: object) -> str | None:
    """取字符串并去掉首尾空白；'null'/'none'/空串都当没有。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "无", "没有"}:
        return None
    return text


class AiChatService:
    """AI 对话服务（只调用模型 + 解析，不碰数据库）。"""

    async def chat(self, payload: AiChatRequest) -> AiChatResponse:
        """处理一轮对话。"""
        message = payload.message.strip()
        if not message:
            raise BusinessError("说点什么吧", code=CODE_PARAM_INVALID)

        if not settings.dashscope_api_key:
            logger.info("AI 对话未配置 Key，返回占位回复（mock）")
            return AiChatResponse(reply=_MOCK_REPLY, intent="chat", actions=[], mock=True)

        body = await self._post_chat(self._build_messages(message, payload.history))
        return self._parse(body)

    # ---------------- 请求组装 ----------------

    @staticmethod
    def _build_messages(message: str, history: list[AiChatTurn]) -> list[dict]:
        """system（含今天的日期）+ 最近几轮历史 + 本轮。"""
        today = date.today().isoformat()
        system = _SYSTEM_PROMPT.replace("{today}", today)

        messages: list[dict] = [{"role": "system", "content": system}]
        for turn in history[-MAX_HISTORY_TURNS:]:
            role = "assistant" if turn.role == "assistant" else "user"
            content = turn.content.strip()[:MAX_HISTORY_CHARS]
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})
        return messages

    async def _post_chat(self, messages: list[dict]) -> dict:
        """调 DashScope 的 OpenAI 兼容接口（文本模型）。"""
        payload = {
            "model": settings.chat_model,
            "messages": messages,
            "temperature": 0,
            # 回复本身很短，限一下长度既省钱也能压住模型"话痨"的倾向
            "max_tokens": 800,
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
            logger.error("调用对话模型失败: %s", exc)
            raise BusinessError("AI 服务暂时不可用，请稍后重试") from exc

    # ---------------- 解析 ----------------

    def _parse(self, body: dict) -> AiChatResponse:
        """从模型回复里抠出 JSON。

        ⚠️ 解析失败**不抛错**：把模型原文当作回复、intent 归到 chat。
        理由——用户的话已经在模型那儿走了一圈，直接报错等于把这次交互整个丢掉；
        而把原文显示出来，用户至少看得到"它在说什么"，也方便我们发现是提示词的问题。
        """
        try:
            content = str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            raise BusinessError("对话结果格式异常")

        data = _load_json_object(content)
        if data is None:
            logger.warning("对话结果不是合法 JSON，降级为纯文本回复：%s", content[:200])
            text = content.strip()
            if not text:
                raise BusinessError("对话结果无法解析")
            return AiChatResponse(reply=text, intent="chat", actions=[])

        reply = _clean_text(data.get("reply")) or "好的。"
        intent = str(data.get("intent") or "chat").strip().lower()
        actions = self._parse_actions(data.get("actions"))

        # 模型说是 log 但一条可用的动作都没抽出来 → 降级成 chat，
        # 否则前端会渲染一张空卡片
        if intent == "log" and not actions:
            intent = "chat"
        if intent not in {"log", "chat", "recommend"}:
            intent = "chat"

        return AiChatResponse(reply=reply, intent=intent, actions=actions)


    @staticmethod
    def _parse_actions(raw: object) -> list[ActionDraft]:
        """校验并转换动作草案。抽不到或字段不可用的直接丢掉，不猜。"""
        if not isinstance(raw, list):
            return []

        today = date.today().isoformat()
        actions: list[ActionDraft] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            if item.get("kind") not in (None, KIND_CREATE_CALORIE_LOG):
                continue  # 本轮只认这一种动作

            food_name = _clean_text(item.get("food_name"))
            if not food_name:
                continue  # 菜名都没有，这条没意义

            calories = _to_float(item.get("calories"))
            if calories is not None and not (0 < calories <= MAX_REASONABLE_KCAL):
                # 超出合理区间基本是听错/多打个 0。不采信，留给用户在卡片上自己填
                logger.warning("热量 %s 超出合理区间，置空", calories)
                calories = None

            actions.append(
                ActionDraft(
                    kind=KIND_CREATE_CALORIE_LOG,
                    food_name=food_name[:64],
                    portion=_clean_text(item.get("portion")),
                    calories=calories,
                    calories_estimated=bool(item.get("calories_estimated")) or calories is None,
                    eaten_at=_safe_date(item.get("eaten_at"), today),
                )
            )
        return actions


def _safe_date(value: object, today: str) -> str:
    """校验模型给的日期：只接受「今天」和「昨天」，其它一律回退到今天。

    为什么只放这两天？
      · 「昨天吃的」在饮食日志里很常见也很合理（用户就是会补记），所以允许；
      · 但再往前（上周、某月某日）就超出本轮"只记当天"的范围了——宁可统一到
        今天，也不要凭空写一个用户没明确说过的日期。
    格式非法同样回退。
    """
    text = _clean_text(value)
    if not text:
        return today
    try:
        parsed = datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return today
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    return parsed.isoformat() if parsed.isoformat() in (today, yesterday) else today


def _load_json_object(text: str) -> dict | None:
    """从模型回复里抠出 JSON 对象。

    模型常在 JSON 外裹一层 ```json ... ``` 或说些多余的话，
    所以不直接 json.loads 整段，而是定位第一个 '{' 和最后一个 '}' 再解析。
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
