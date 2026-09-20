"""AI 对话（本轮落地：用一句话记账）。

职责很单一：把用户这一句（加少量历史）交给模型，拿回一个结构化 JSON ——
「自然语言回复」+「动作草案」，然后返回给前端。

⭐ **这个服务不写业务数据。**
   写库发生在用户点确认卡片之后，由前端调**已有的** /users/me/calorie-logs 完成。
   为什么这么切？见 schemas/ai_chat.py 的模块注释——模型只给"提议权"，
   出错了最多是卡片显示错，不会把脏数据写进用户的记录里。
   （对话消息本身会存进 ai_chat_messages，但那是对话的**记录**，不是业务数据。）

上下文从哪来（2026-09-18 起）：
    **后端自己从 ai_chat_messages 取最近几条**，前端不再传 history——
    传的话就变成"前端负责记忆"，换个设备/刷新一下上下文就没了。
    只有模型调用成功才落库（用户一句 + AI 一句一起存）：
    失败的那轮不存，不然用户重试一次就多一条重复消息。

HTTP 调用照抄 vision_service 的形态：httpx 直连 OpenAI 兼容接口，
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
from app.models.ai_chat import AiChatMessage
from app.repositories.ai_chat_repo import AiChatRepository
from app.schemas.ai_chat import ActionDraft, AiChatRequest, AiChatResponse, AiChatTurn
from app.services import ai_quota_service, nutrition_service

logger = logging.getLogger(__name__)

# 上下文最多带几条消息：只用来消解"再加一碗"这类省略句，带太多既费 token 又容易带偏。
# （一条 = 用户一句或 AI 一句；6 条大约等于三轮对话）
MAX_HISTORY_TURNS = 6
# 给前端回放用的条数上限：对话页一次拉这么多，够翻也不至于一次拖回几百条
MAX_LIST_LIMIT = 100
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

# 当第一级（MCP 查《中国食物成分表》）命中时，追加这段说明 + 查到的数据。
#
# ⭐ 为什么要把它塞进 prompt，而不是在后端直接算好热量？
#    因为用户说的往往是**成品菜**（红烧肉），而查到的是**生食材**（猪肉 395 kcal/100g）。
#    从"生食材"到"成品菜"要按烹饪方式做修正（红烧有糖有油、清蒸几乎不加油），
#    这个判断只有大模型做得了。后端只负责把**权威基准值**喂给它，不越俎代庖。
#
# ⭐ 为什么强调"不要直接用这个数"？
#    因为 395 kcal/100g 是**生猪肉**的值，红烧肉成品通常更低（出油、被稀释）。
#    如果不提醒，模型很可能直接把 395×3=1185 当成 300g 红烧肉的热量，高得离谱。
_NUTRITION_HINT = """
【重要：这条消息的菜名已经查到权威数据了】
用户提到的「{dish}」在《中国食物成分表》里对应的是「{matched}」，
它的营养数据是（每 100 克）：能量 {energy} 千卡。

⚠️ 这是**食材本身**的数据，不是成品菜。请按下面的规则处理：
- 如果用户说的就是食材（如"吃了鸡蛋""喝了牛奶"），**直接用它**：
  热量 = {energy} × (份量克数 / 100)，并把 calories_estimated 填 false。
- 如果用户说的是**加工后的菜**（红烧肉、糖醋排骨、炸鸡…），
  要按烹饪方式做修正：红烧/糖醋 +糖油约 1.1~1.3 倍，油炸约 1.5~2 倍，
  清蒸/水煮/凉拌约 0.8~0.9 倍。修正后 calories_estimated 填 true。
- 无论哪种，都**不要**在 reply 里提到"食物成分表""数据库"这类技术词，
  就像家人说话一样自然。但如果是修正过的，要照旧说一句"热量是我估的"。
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
    """AI 对话服务：调模型 + 解析 + 读写对话历史。业务数据的写入不在这里。"""

    def __init__(self, repo: AiChatRepository) -> None:
        self.repo = repo

    async def chat(self, user_id: int, payload: AiChatRequest) -> AiChatResponse:
        """处理一轮对话：取上下文 → 调模型 → 成功后把这一轮存进历史。"""
        message = payload.message.strip()
        if not message:
            raise BusinessError("说点什么吧", code=CODE_PARAM_INVALID)

        if not settings.chat_api_key_effective:
            logger.info("AI 对话未配置 Key，返回占位回复（mock）。本轮不落库")
            return AiChatResponse(reply=_MOCK_REPLY, intent="chat", actions=[], mock=True)

        # ① 配额：调模型前先消耗一次。超限会抛 BusinessError，由全局处理器转成响应。
        #    ⚠️ 放在"没配 Key"检查之后——没配 Key 时根本不花钱，不该占额度。
        ai_quota_service.consume(user_id)

        # 上下文后端自己取：不依赖前端记性，换设备/刷新页面都不断片
        recent = await self.repo.list_recent(user_id, MAX_HISTORY_TURNS)
        history = [AiChatTurn(role=m.role, content=m.content) for m in recent]

        # ② 营养数据：能从权威数据源查到就把基准值喂给模型，查不到就退化成纯估算。
        #    ⚠️ 这一步**绝不抛异常**（nutrition_service 内部已吞掉所有异常），
        #       最坏情况是返回 None，与改造前的行为完全一致。
        nutrition = await self._lookup_nutrition(message)

        body = await self._post_chat(self._build_messages(message, history, nutrition))
        result = self._parse(body, nutrition)

        # 成功才落库，两句一起存（user 一句 + assistant 一句）
        await self.repo.add_user_message(user_id, message)
        await self.repo.add_assistant_message(
            user_id,
            result.reply,
            [action.model_dump() for action in result.actions],
        )
        return result

    @staticmethod
    async def _lookup_nutrition(message: str) -> nutrition_service.FoodNutrition | None:
        """从用户这句话里抠出菜名，去查权威营养数据。

        ⚠️ 为什么在这里抠菜名，而不是等模型返回结果再查？
           因为营养数据要**在调模型之前**准备好并塞进 prompt——
           模型看到基准值才能做烹饪方式修正。反过来的话就得调两次模型。
        """
        dish = _extract_dish_name(message)
        if not dish:
            return None
        try:
            return await nutrition_service.lookup_food_nutrition(dish)
        except Exception as exc:
            # nutrition_service 已经兜过一层了，这里是最后保险
            logger.warning("营养查询异常（不影响本轮对话）：%s", exc)
            return None

    async def list_messages(self, user_id: int, limit: int) -> list[AiChatMessage]:
        """取某用户的最近对话（给前端回放）。limit 做了上限保护。"""
        return await self.repo.list_recent(user_id, max(1, min(limit, MAX_LIST_LIMIT)))

    async def clear_messages(self, user_id: int) -> int:
        """清空某用户的全部对话（「新对话」）。返回删掉的条数。"""
        return await self.repo.delete_all(user_id)

    # ---------------- 请求组装 ----------------

    @staticmethod
    def _build_messages(
        message: str,
        history: list[AiChatTurn],
        nutrition: nutrition_service.FoodNutrition | None = None,
    ) -> list[dict]:
        """system（含今天的日期）+ 最近几轮历史 + 本轮。

        `nutrition` 不为空时，在用户消息后面追加一段"已查到权威数据"的提示。
        ⚠️ 追加在**用户消息同一条**里（而不是单独一条 system），
           是为了让模型把它当成本轮的输入上下文，而不是全局规则。
        """
        today = date.today().isoformat()
        system = _SYSTEM_PROMPT.replace("{today}", today)

        messages: list[dict] = [{"role": "system", "content": system}]
        for turn in history[-MAX_HISTORY_TURNS:]:
            role = "assistant" if turn.role == "assistant" else "user"
            content = turn.content.strip()[:MAX_HISTORY_CHARS]
            if content:
                messages.append({"role": role, "content": content})

        user_content = message
        if nutrition is not None:
            hint = _NUTRITION_HINT.format(
                dish=message,
                matched=nutrition.matched_name,
                energy=nutrition.energy_kcal_per_100g,
            )
            user_content = f"{message}\n{hint}"

        messages.append({"role": "user", "content": user_content})
        return messages

    async def _post_chat(self, messages: list[dict]) -> dict:
        """调对话模型的 OpenAI 兼容接口。

        接入点/密钥用 chat 专属配置（缺省回落 DashScope 共用值）——
        将来"对话走本地模型、识图走云"时就改这两个配置，这里不用动。
        """
        payload = {
            "model": settings.chat_model,
            "messages": messages,
            "temperature": 0,
            # 回复本身很短，限一下长度既省钱也能压住模型"话痨"的倾向
            "max_tokens": 800,
        }
        headers = {
            "Authorization": f"Bearer {settings.chat_api_key_effective}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.chat_base_url_effective}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            logger.error("调用对话模型失败: %s", exc)
            raise BusinessError("AI 服务暂时不可用，请稍后重试") from exc

    # ---------------- 解析 ----------------

    def _parse(
        self,
        body: dict,
        nutrition: nutrition_service.FoodNutrition | None = None,
    ) -> AiChatResponse:
        """从模型回复里抠出 JSON。

        ⚠️ 解析失败**不抛错**：把模型原文当作回复、intent 归到 chat。
        理由——用户的话已经在模型那儿走了一圈，直接报错等于把这次交互整个丢掉；
        而把原文显示出来，用户至少看得到"它在说什么"，也方便我们发现是提示词的问题。

        `nutrition` 用来标注动作草案的 `source`：
        命中了权威数据源（且模型没有做烹饪修正）→ 标成"查的"；否则标成"估的"。
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
        actions = self._parse_actions(data.get("actions"), nutrition)

        # 模型说是 log 但一条可用的动作都没抽出来 → 降级成 chat，
        # 否则前端会渲染一张空卡片
        if intent == "log" and not actions:
            intent = "chat"
        if intent not in {"log", "chat", "recommend"}:
            intent = "chat"

        return AiChatResponse(reply=reply, intent=intent, actions=actions)


    @staticmethod
    def _parse_actions(
        raw: object,
        nutrition: nutrition_service.FoodNutrition | None = None,
    ) -> list[ActionDraft]:
        """校验并转换动作草案。抽不到或字段不可用的直接丢掉，不猜。

        `source` 怎么定：
          · 这次查到了权威数据，且模型认为这个热量**不是估的**
            （说明它直接用了查到的值，没做烹饪修正）→ `mcp_exact`
          · 查到了权威数据，但模型说"是估的"（说明它做了修正）
            → `mcp_derived`
          · 压根没查到 / MCP 没开 → `llm_estimate`

        ⚠️ 这里**不重算热量**，只做标注。热量的值以模型给的为准——
           因为它可能已经按烹饪方式修正过了，后端硬算反而会覆盖掉正确结果。
        """
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

            estimated = bool(item.get("calories_estimated")) or calories is None

            # 标注来源
            if nutrition is None:
                source = nutrition_service.SOURCE_LLM_ESTIMATE
                matched_food = None
            elif estimated:
                # 有基准值但模型做了修正（或热量缺失）
                source = nutrition_service.SOURCE_MCP_DERIVED
                matched_food = nutrition.matched_name
            else:
                # 有基准值且模型认为不用估 → 它直接用了查到的数据
                source = nutrition_service.SOURCE_MCP_EXACT
                matched_food = nutrition.matched_name

            actions.append(
                ActionDraft(
                    kind=KIND_CREATE_CALORIE_LOG,
                    food_name=food_name[:64],
                    portion=_clean_text(item.get("portion")),
                    calories=calories,
                    calories_estimated=estimated,
                    eaten_at=_safe_date(item.get("eaten_at"), today),
                    source=source,
                    matched_food=matched_food,
                )
            )
        return actions


#: 从用户这句话里提取菜名用的模式。
#:
#: ⚠️ 这是**启发式**，目的是"能抠出个差不多的词去查"，不是精确理解。
#:    抠错了最坏结果是查不到（返回 None），然后退化成原来的纯估算——
#:    和改造前完全一样，不会更差。这是敢用启发式的前提。
#:
#: 匹配形如：「中午吃了红烧肉500g」「刚吃了个苹果」「喝了碗米饭」
#:          「土豆炖牛肉怎么做」「清蒸鲈鱼的做法」
_DISH_PATTERNS = (
    # "吃了/喝了/吃了个/喝了碗 X" —— X 取到标点、数字、空格为止
    re.compile(r"[吃喝](?:了|过)?(?:个|碗|份|杯|盘|块|只|条|根|斤|些|点)?\s*([^\s，。,.！!？?0-9]{1,12})"),
    # "来个 X" / "点了 X"
    re.compile(r"(?:来个|点了|要了)\s*([^\s，。,.！!？?0-9]{1,12})"),
    # ⭐ "X怎么做 / X的做法 / X怎么做才好吃" —— **最常见的提问方式**
    #
    #    为什么必须单独列一条：
    #      用户自己举的例子就是"土豆炖牛肉怎么做"。这句话里没有任何
    #      "吃/喝/来/点"的动词，前两条模式全都匹配不上，结果就是
    #      "用户问了一道很具体的菜，我们却什么都没查"。
    #      而"怎么做"恰恰是**最该去查营养成分的场景**——用户就是想知道这道菜怎么样。
    #
    #    开头用 `[^\s，。,.！!？?]{2,12}` 而不是 `\w+`：菜名里可能有
    #    "炖""烧"这类词，要一起带上（"土豆炖牛肉"不能只抠出"牛肉"）。
    #    限定 2~12 字，避免把整句话都吞进来。
    re.compile(r"([^\s，。,.！!？?]{2,12}?)(?:怎么做|的做法|咋做|如何做|怎么做才好吃)"),
)

#: 这些词抠出来没意义（是"什么""啥"这类疑问词，或常见动词），直接丢掉。
_DISH_STOPWORDS = frozenset(
    {"什么", "啥", "东西", "点儿", "点", "些", "饭", "的", "了", "个", "碗", "什么好", "啥好"}
)

#: 抠出来的词里含这些字 → 基本不是菜名，别浪费一次 MCP 往返。
#:
#: ⚠️ 实测踩过："我吃了个那个东西" 会抠出 "那个东西"，
#:    然后真的去问 MCP 一次（虽然有缓存，但首次是实打实的子进程往返）。
#:    与其靠"查不到再退回"，不如在这里先挡掉明显不是菜名的。
_NOT_DISH_CHARS = ("那个", "这个", "什么", "啥", "东西")

#: 抠出来的菜名太短/太长都不要
_MIN_DISH_LEN = 2
_MAX_DISH_LEN = 12


def _extract_dish_name(message: str) -> str | None:
    """从用户这句话里尽量抠出一个"菜名"，用来查权威营养数据。

    抠不到就返回 None（调用方跳过查询，退化成纯估算）。
    """
    text = (message or "").strip()
    if not text:
        return None

    for pattern in _DISH_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        candidate = match.group(1).strip()
        if not (_MIN_DISH_LEN <= len(candidate) <= _MAX_DISH_LEN):
            continue
        if candidate in _DISH_STOPWORDS:
            continue
        # 含"那个/这个/什么"这类指示代词的，基本不是菜名
        if any(word in candidate for word in _NOT_DISH_CHARS):
            continue
        return candidate

    return None


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
