"""AI 对话：一个会用工具的 Agent。

⭐ 这一版把「写死的流程」换成了「模型自己决定」（2026-09-21）：

    改造前：
        正则抠菜名 → 查热量 → 拼 prompt → 调一次模型 → 解析 JSON
        每一步都是代码写死的。所以"今天吃什么"它只能回"我还在学"——
        不是它不想答，是它手里**根本没有工具**。
        而那个用来抠菜名的正则，前后改了三版还有漏（"怎么做"那类句式
        一开始完全匹配不上）。

    改造后：
        把工具交出去，让模型自己决定调不调、调哪个、调几次。
        正则整块删掉了——**能用模型判断的事，就别拿正则硬凑**。

⭐ 关于职责边界（这条从改造前一直保留到现在）：
   **这个服务不写业务数据。**
   写库发生在用户点确认卡片之后，由前端调**已有的** /users/me/calorie-logs 完成。
   模型只给"提议权"，出错了最多是卡片显示错，不会把脏数据写进用户的记录里。
   所以工具清单里**一个写操作都没有**——查冰箱、查菜单、查热量，
   全是只读的。

⭐ 权限：`space_id` 是客户端传的，**不能信**。
   跑 Agent 之前先过 `ensure_member`；工具执行时再走一遍 service 层。
   两道闸用的都是同一份规则（见 MenuQueryService.ensure_member 的说明）。

上下文从哪来（2026-09-18 起）：
    **后端自己从 ai_chat_messages 取最近几条**，前端不再传 history——
    传的话就变成"前端负责记忆"，换个设备/刷新一下上下文就没了。
    只有模型调用成功才落库（用户一句 + AI 一句一起存）：
    失败的那轮不存，不然用户重试一次就多一条重复消息。

HTTP 调用照抄 vision_service 的形态：httpx 直连 OpenAI 兼容接口
（所以换成 DeepSeek 只是改 CHAT_BASE_URL / CHAT_MODEL，代码不动），
temperature 走配置（不同模型要求不一样），
HTTP 错误 → BusinessError（不静默失败），没配 Key → 占位 + mock=True（前端会明说是演示）。
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import date, datetime, timedelta

import httpx

from app.agent import react
from app.agent.prompts import REFORMAT_INSTRUCTION, build_system_prompt
from app.agent.tools import ToolContext
from app.core.config import settings
from app.core.exceptions import BusinessError
from app.core.response import CODE_PARAM_INVALID, CODE_SERVER_ERROR
from app.models.ai_chat import AiChatMessage
from app.models.user import User
from app.repositories.ai_chat_repo import AiChatRepository
from app.schemas.ai_chat import (
    ActionDraft,
    AgentStepInfo,
    AiChatRequest,
    AiChatResponse,
    AiChatTurn,
)
from app.services import ai_quota_service, nutrition_service
from app.services.menu_query_service import MenuQueryService

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


def _to_float(value: object) -> float | None:
    """把模型给的值转成数字，容忍 '约550kcal' / '500 克' 这类带杂质的写法。"""
    if isinstance(value, bool):  # bool 是 int 的子类，先挡掉
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _clean_text(value: object) -> str | None:
    """把可选文本规整一下：非字符串、空白一律当"没给"。"""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


class AiChatService:
    """AI 对话服务：跑 Agent + 解析 + 读写对话历史。业务数据的写入不在这里。"""

    def __init__(self, repo: AiChatRepository, session: object) -> None:
        self.repo = repo
        # ⚠️ Agent 的工具要查库（冰箱、菜单），所以这里必须拿到 session。
        #    改造前不需要它——那时候 AI 只做"从一句话抽字段"，碰不到业务数据。
        self.session = session

    async def chat(
        self,
        user: User,
        payload: AiChatRequest,
        on_step: react.StepCallback | None = None,
    ) -> AiChatResponse:
        """处理一轮对话：校验家庭组 → 跑 Agent → 成功后把这一轮存进历史。

        `on_step`（可选）：透传给 Agent 循环，每执行完一个工具回调一次
        （流式通道用；传 None 行为与非流式完全一致）。
        """
        message = payload.message.strip()
        if not message:
            raise BusinessError("说点什么吧", code=CODE_PARAM_INVALID)

        if not settings.chat_api_key_effective:
            logger.info("AI 对话未配置 Key，返回占位回复（mock）。本轮不落库")
            return AiChatResponse(reply=_MOCK_REPLY, intent="chat", actions=[], mock=True)

        # ① 配额：调模型前先消耗一次。
        #    ⚠️ **一轮对话只算一次**，而不是 Agent 每调一次模型/工具都算一次——
        #       用户感知的是"我问了一句话"，中间绕几圈是我的实现细节。
        #    ⚠️ 放在"没配 Key"检查之后——没配 Key 时根本不花钱，不该占额度。
        ai_quota_service.consume(user.id)

        # ② 家庭组：客户端传上来的，**不能信**。先验一遍是不是这家人，
        #    越权的请求在这里就被挡掉，不用绕到工具里才发现。
        space_id = await self._resolve_space_id(user, payload.space_id)

        # 上下文后端自己取：不依赖前端记性，换设备/刷新页面都不断片
        recent = await self.repo.list_recent(user.id, MAX_HISTORY_TURNS)
        history = [AiChatTurn(role=m.role, content=m.content) for m in recent]
        messages = self._build_messages(message, history)

        # ③ 跑 Agent：模型自己决定查什么。
        ctx = ToolContext(session=self.session, user=user, space_id=space_id)
        run_result = await react.run(messages, ctx, self._call_model, on_step=on_step)

        # ④ 兜住输出契约：模型偶尔会用大白话回答（调完工具之后尤其容易），
        #    这里补一次把话"重排版"成 JSON。理由见 _ensure_json 的注释。
        content = await self._ensure_json(run_result.content, messages)

        # ⑤ 解析。
        #    `nutrition` 从**实际执行过的工具**里还原——这样 source 标注是
        #    "确实查到了"这个事实决定的，而不是模型自己说它查了。
        nutrition = _nutrition_from_steps(run_result.steps)
        result = self._parse(content, nutrition, run_result.steps)

        # 成功才落库，两句一起存（user 一句 + assistant 一句）
        await self.repo.add_user_message(user.id, message)
        await self.repo.add_assistant_message(
            user.id,
            result.reply,
            [action.model_dump() for action in result.actions],
        )
        return result

    async def chat_stream(
        self,
        user: User,
        payload: AiChatRequest,
    ) -> AsyncGenerator[tuple[str, dict], None]:
        """流式版的一轮对话：**工具步骤在发生时就吐出来**，最后再给整包结果。

        ⭐ 为什么值得单独一条流式通道：
           一轮 Agent 最多 4 次串行模型调用，前后 10 秒起步，用户全程只看到一个转圈。
           把"查冰箱 → 查到了"这类步骤**实时**推给前端，
           等待就从黑盒变成了看得见的进度——总时长没变，感知完全不同。

        产出与传输无关的 `(event, data)` 二元组（SSE 编码交给接口层）：
          · start    连接建立（首字节立刻到，前端据此知道"接上了"）
          · step     一步工具执行完成（形状与 AgentStepInfo 一致）
          · message  最终整包（**与 /ai/chat 的返回结构完全一致**，
                     所以前端渲染、落库、回放逻辑零改动）
          · error    失败（流式响应的 HTTP 头在开始时就以 200 发出，
                     业务错误只能走事件通道告诉前端）
          · done     收尾

        ⭐ asyncio.Queue 是"回调 → 生成器"的桥：
           Python 的生成器不能从普通回调里 yield，
           所以 on_step 把步骤事件推进队列，由本生成器作为唯一消费者往外吐。
        """
        yield "start", {}

        queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

        async def on_step(step: react.AgentStep) -> None:
            await queue.put((
                "step",
                {
                    "tool": step.tool,
                    "ok": step.ok,
                    "detail": step.detail,
                    "arguments": step.arguments,
                },
            ))

        async def runner() -> AiChatResponse | None:
            """跑完整轮对话；异常在这里就地转成 error 事件，不让它炸掉流。"""
            try:
                return await self.chat(user, payload, on_step=on_step)
            except BusinessError as exc:
                await queue.put(("error", {"code": exc.code, "message": exc.message}))
                return None
            except Exception:
                logger.exception("流式对话失败")
                await queue.put((
                    "error",
                    {"code": CODE_SERVER_ERROR, "message": "AI 服务暂时不可用，请稍后重试"},
                ))
                return None
            finally:
                await queue.put(None)  # 哨兵：消费循环据此收尾

        task = asyncio.create_task(runner())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item

            # 循环正常走完才取结果；runner 已经把异常都转成了 error 事件
            result = await task
        finally:
            # 客户端中途断开时，本生成器会被 CancelledError / GeneratorExit 打断——
            # 必须把 runner 一并取消，否则它会变成无人认领的孤儿任务，
            # 拿着用户的额度把剩下的模型调用烧完。
            if not task.done():
                task.cancel()

        if result is not None:
            yield "message", result.model_dump()
            yield "done", {}

    async def _resolve_space_id(self, user: User, raw: object) -> int | None:
        """把客户端传的家庭组解析成 int 并校验成员身份。

        ⚠️ 为什么**校验失败就直接报错**，而不是"悄悄当没传"？
           因为这不是用户输入错误，是客户端给了个不该给的值（要么是前端 bug，
           要么是有人在试探）。静默降级会把越权尝试伪装成"正常但查不到"。
        """
        text = str(raw).strip() if raw is not None else ""
        if not text:
            # 前端没传也不报错：闲聊、记账这些根本用不到家庭组。
            # 真需要查冰箱时，工具会返回一句"还没确定要查哪个家庭组"交给模型追问。
            return None

        try:
            space_id = int(text)
        except ValueError as exc:
            raise BusinessError("家庭组参数不对", code=CODE_PARAM_INVALID) from exc

        await MenuQueryService(self.session).ensure_member(user, space_id)
        return space_id

    async def list_messages(self, user_id: int, limit: int) -> list[AiChatMessage]:
        """取某用户的最近对话（给前端回放）。limit 做了上限保护。"""
        return await self.repo.list_recent(user_id, max(1, min(limit, MAX_LIST_LIMIT)))

    async def clear_messages(self, user_id: int) -> int:
        """清空某用户的全部对话（「新对话」）。返回删掉的条数。"""
        return await self.repo.delete_all(user_id)

    # ---------------- 请求组装 ----------------

    @staticmethod
    def _build_messages(message: str, history: list[AiChatTurn]) -> list[dict]:
        """system + 最近几轮历史 + 本轮。

        ⚠️ 改造后这里**不再往用户消息后面塞"查到权威数据"的提示**了——
           查数据从"后端写死的步骤"变成了"模型自己调的工具"，
           结果由工具返回，天然就在对话里。
        """
        system = build_system_prompt(date.today().isoformat())

        messages: list[dict] = [{"role": "system", "content": system}]
        for turn in history[-MAX_HISTORY_TURNS:]:
            role = "assistant" if turn.role == "assistant" else "user"
            content = turn.content.strip()[:MAX_HISTORY_CHARS]
            if content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})
        return messages

    async def _call_model(
        self,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> dict:
        """调对话模型，返回这一轮的 assistant 消息（可能带 tool_calls）。

        接入点/密钥用 chat 专属配置（缺省回落 DashScope 共用值）——
        换成 DeepSeek 就是改这三个环境变量，这里一行不用动。

        ⚠️ `tools` 为 None 时**整个省略这个字段**，不是传 null——
           OpenAI 兼容接口对显式 `"tools": null` 的反应并不一致。
        """
        payload: dict = {
            "model": settings.chat_model,
            "messages": messages,
            "temperature": settings.chat_temperature,
            # 回复本身很短（一个 JSON），限一下长度既省钱也能压住模型"话痨"的倾向
            "max_tokens": 800,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

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
                body = resp.json()
        except httpx.HTTPError as exc:
            logger.error("调用对话模型失败: %s", exc)
            raise BusinessError("AI 服务暂时不可用，请稍后重试") from exc

        try:
            return body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BusinessError("对话结果格式异常") from exc

    async def _ensure_json(self, content: str, messages: list[dict]) -> str:
        """确保最终拿到的是 JSON；模型漂了就**再问它一次**把它重排版成 JSON。

        ⭐ 这个补救为什么值得多花一次调用？
           因为漂移丢的是**结构化部分**：action 草案没了，前端就渲染不出确认卡片，
           "记一笔热量"这个核心功能会**静默失效**——用户看到一句正常的回复，
           却永远点不到「记下」。这比"回复丑一点"严重得多，而且很难被发现。

        ⚠️ 补救失败（比如模型又漂了、或者网络抖了）**不抛错**：
           沿用原文，至少用户能看到它在说什么。宁可降级，也不要把这次交互整个丢掉。

        ⚠️ 补救请求带上完整对话上下文（含工具结果），
           这样它重排版时用的是同样的信息，不会凭空换一个答案。
        """
        if _load_json_object(content) is not None:
            return content

        logger.info("模型输出不是 JSON，尝试重排版一次")
        retry_messages = [
            *messages,
            {"role": "assistant", "content": content},
            {"role": "user", "content": REFORMAT_INSTRUCTION},
        ]
        try:
            message = await self._call_model(retry_messages, None)
        except BusinessError as exc:
            logger.warning("重排版调用失败，沿用原文：%s", exc)
            return content

        fixed = message.get("content") if isinstance(message.get("content"), str) else ""
        if _load_json_object(fixed) is None:
            logger.warning("重排版后仍不是 JSON，沿用原文")
            return content
        return fixed

    # ---------------- 解析 ----------------

    def _parse(
        self,
        content: str,
        nutrition: nutrition_service.FoodNutrition | None = None,
        steps: list[react.AgentStep] | None = None,
    ) -> AiChatResponse:
        """从模型最终输出里抠出 JSON。

        ⚠️ 解析失败**不抛错**：把模型原文当作回复、intent 归到 chat。
        理由——用户的话已经在模型那儿走了一圈，直接报错等于把这次交互整个丢掉；
        而把原文显示出来，用户至少看得到"它在说什么"，也方便我们发现是提示词的问题。
        """
        step_infos = [
            AgentStepInfo(
                tool=step.tool,
                ok=step.ok,
                detail=step.detail,
                arguments=step.arguments,
            )
            for step in (steps or [])
        ]

        data = _load_json_object(content)
        if data is None:
            logger.warning("对话结果不是合法 JSON，降级为纯文本回复：%s", content[:200])
            text = content.strip()
            if not text:
                raise BusinessError("对话结果无法解析")
            # ⚠️ 降级时**也要把 steps 带上**：用户至少能看到"它查了但没吐出结构化结果"，
            #    这比一个加载失败的空框有用得多。
            return AiChatResponse(reply=text, intent="chat", actions=[], steps=step_infos)

        reply = _clean_text(data.get("reply")) or "好的。"
        intent = str(data.get("intent") or "chat").strip().lower()
        actions = self._parse_actions(data.get("actions"), nutrition)

        # 模型说是 log 但一条可用的动作都没抽出来 → 降级成 chat，
        # 否则前端会渲染一张空卡片
        if intent == "log" and not actions:
            intent = "chat"
        # 改造后 recommend 是**真的会用了**（模型能查冰箱和菜单再推荐），
        # 所以这里不再降级它，只挡掉不认识的取值。
        if intent not in {"log", "chat", "recommend"}:
            intent = "chat"

        return AiChatResponse(reply=reply, intent=intent, actions=actions, steps=step_infos)

    @staticmethod
    def _parse_actions(
        raw: object,
        nutrition: nutrition_service.FoodNutrition | None = None,
    ) -> list[ActionDraft]:
        """校验并转换动作草案。抽不到或字段不可用的直接丢掉，不猜。

        `source` 怎么定（由**后端**根据实际执行过的工具判定，不是模型自己说的）：
          · 这次查到了权威数据，且模型认为这个热量**不是估的**
            （说明它直接用了查到的值，没做烹饪修正）→ `mcp_exact`
          · 查到了权威数据，但模型说"是估的"（说明它做了修正）
            → `mcp_derived`
          · 压根没查到 / MCP 没开 / 模型没查 → `llm_estimate`

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


def _nutrition_from_steps(steps: list[react.AgentStep]) -> nutrition_service.FoodNutrition | None:
    """从 Agent 实际调过的工具里，还原出"这轮查到的热量基准值"。

    ⭐ 为什么不直接让模型在 JSON 里报一个 source？
       因为那是**模型的自述**，它可以编。而这里还原的是**真实发生过的事实**：
       工具确实被调了、确实查到了、查到的是什么。
       用来标注"这个数字是查的还是估的"，必须以后者为准。

    查不到 / 没查 / 工具失败，一律返回 None（上层会标成 `llm_estimate`）。
    """
    for step in steps:
        if step.tool != "lookup_nutrition" or not step.ok:
            continue
        data = step.data
        if not data.get("found"):
            return None
        energy = _to_float(data.get("energy_kcal_per_100g"))
        matched = _clean_text(data.get("matched_name"))
        if energy is None or not matched:
            return None
        return nutrition_service.FoodNutrition(
            matched_name=matched,
            energy_kcal_per_100g=energy,
            # 工具自己知道数据来自哪一级（mcp_exact / mcp_derived）。
            # 这里标 exact 表示"确实是查到的"，和上面 source 的语义是两件事：
            # 这里是"查到没查到"，ActionDraft.source 是"最终这个数字怎么来的"。
            source=nutrition_service.SOURCE_MCP_EXACT,
        )
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
