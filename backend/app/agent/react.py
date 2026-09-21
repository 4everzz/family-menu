"""ReAct 循环：让模型「想 → 调工具 → 看结果 → 再想」，直到给出最终回答。

⭐ 改造前后最大的差别就是**谁决定流程**：

    改造前（写死的流程）：
        正则抠菜名 → 查热量 → 拼 prompt → 调一次模型 → 解析 JSON
        每一步都是代码写死的，模型没有选择权。"今天吃什么"它只能回"我还在学"，
        因为它手里根本没有工具。

    改造后（这个循环）：
        调模型 → 它说"我要查冰箱" → 我们去查 → 结果回给它 → 它再决定下一步
        → 直到它直接给出回答。
        **调不调、调哪个、调几次，由模型决定。**

⚠️ 必须设上限（`MAX_STEPS`）。模型有可能陷进"再查一次"的循环里，
   每绕一圈都是真金白银的 token。所以最后一轮**不给工具**，逼它出结果——
   这样最多花 `MAX_STEPS` 次调用，而不是"直到它想通为止"。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.agent import tools
from app.agent.tools import ToolContext

logger = logging.getLogger(__name__)

#: 最多调用模型几次（注意：**不是"最多调几轮工具"**）。
#:
#: 为什么是 4？—— 现实里最复杂的问法是
#: 「今天吃什么」→ 查冰箱 → 查菜谱 → 查分类（筛选用）→ 出答案，
#: 3 轮工具就够。再加 1 次"收口调用"，所以 4。
#: 也就是说**实际可用的工具轮次是 MAX_STEPS - 1 = 3**。
#:
#: ⚠️ 为什么必须设上限？模型有可能陷进"再查一次"的循环里，每绕一圈都是真金白银。
#:    所以最后一轮**不给工具**，逼它用已有信息出结果——
#:    这样正常情况最多花 MAX_STEPS 次调用，而不是"直到它想通为止"。
MAX_STEPS = 4

#: 模型调用器的签名。
#: `tools` 为 None 时**必须整个省略**这个字段（不是传 null）——
#: OpenAI 兼容接口对显式的 `"tools": null` 反应不一致，有的直接报错。
ModelCaller = Callable[[list[dict[str, Any]], list[dict[str, Any]] | None], Awaitable[dict]]


@dataclass
class AgentStep:
    """一步工具调用。存在的意义主要是**给用户看**：
    让前端能显示"它查了冰箱、又查了热量"，而不是凭空冒出一段话。"""

    tool: str
    arguments: dict[str, Any]
    ok: bool
    detail: str
    #: 工具返回的**原始结果**。
    #: ⚠️ 只给后端自己用（比如上层要从"查热量"那一步的结果里还原出
    #:    `source` 标注），**不要直接塞进接口响应**——里面可能有整份食材清单，
    #:    会把响应撑大。响应里只带 tool/ok/detail 这三个轻量字段。
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """一轮 Agent 跑完的结果。"""

    #: 模型最终的输出原文（本项目的约定是 JSON 字符串，由上层解析）
    content: str
    steps: list[AgentStep] = field(default_factory=list)
    #: 是否"工具轮次用光、被强制收口"。用于排查提示词是不是引导得不好。
    hit_step_limit: bool = False


async def run(
    messages: list[dict[str, Any]],
    ctx: ToolContext,
    call_model: ModelCaller,
    max_steps: int = MAX_STEPS,
) -> AgentResult:
    """跑完一轮完整的 Agent 对话。

    ⚠️ `messages` **会被就地修改**（往里追加 assistant / tool 消息）。
       这是有意的：调用方如果想保留原始消息，自己传一份副本进来。
    """
    steps: list[AgentStep] = []

    # 每跑一轮循环 = 最多一次模型调用 + 若干次工具调用
    for index in range(max_steps):
        last_chance = index == max_steps - 1

        # ⭐ 最后一轮不给工具：逼它用已有信息回答。
        #    这比"超时后再补一次调用"省一次调用，也避免它又开一轮查询。
        message = await call_model(messages, None if last_chance else tools.TOOL_SPECS)

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            # 正常收口：模型觉得信息够了，直接给回答
            return AgentResult(content=_content_of(message), steps=steps)

        messages.append(_assistant_message(message, tool_calls))
        steps.extend(await _run_tool_calls(tool_calls, ctx, messages))

    # 走到这里说明"最后一轮（已经不给工具了）它还要调工具"——
    # 属于反常情况，但得有兜底：再要一次回答，不再给工具。
    logger.warning("Agent 达到最大轮次仍在请求工具，强制收口 | steps=%s", len(steps))
    final = await call_model(messages, None)
    return AgentResult(
        content=_content_of(final),
        steps=steps,
        hit_step_limit=True,
    )


async def _run_tool_calls(
    tool_calls: list[dict[str, Any]],
    ctx: ToolContext,
    messages: list[dict[str, Any]],
) -> list[AgentStep]:
    """执行这一轮模型要的所有工具，并把结果**按协议格式**追加回 messages。

    ⚠️ 每个 tool_call 都要有对应的 `role: "tool"` 消息，数量一个不能少——
       少一个，下一次调用会因为"assistant 说要调 2 个工具、只回了 1 个结果"
       而直接报错。所以即使工具失败，也要回一条（内容是错误说明）。
    """
    steps: list[AgentStep] = []

    for call in tool_calls:
        function = call.get("function") or {}
        name = str(function.get("name") or "")
        raw_arguments = function.get("arguments")
        call_id = str(call.get("id") or "")

        # tools.execute 内部已经把异常都转成 {"ok": False, "error": ...} 了，
        # 但这里再包一层是**有必要的**：万一哪天有人改坏了 execute，
        # 抛出来的异常会让下面那条 tool 消息**根本不会被 append**，
        # 于是下一次模型调用会因为"assistant 说要调工具、却没有任何结果回来"
        # 而直接报协议错误——一个工具的小毛病，升级成整轮对话失败。
        try:
            result = await tools.execute(name, raw_arguments, ctx)
        except Exception as exc:  # noqa: BLE001 —— 兜底，保证协议消息一定发出
            logger.exception("工具执行时抛出了未捕获的异常 | tool=%s", name)
            result = {
                "ok": False,
                "error": f"这个查询出错了（{type(exc).__name__}）。请如实告诉用户没查到。",
            }

        steps.append(
            AgentStep(
                tool=name,
                arguments=tools.parse_arguments(raw_arguments) or {},
                ok=bool(result.get("ok")),
                detail=_summarize(name, result),
                data=result,
            )
        )

        messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": _dump(result),
            }
        )

    return steps


def _assistant_message(message: dict[str, Any], tool_calls: list[dict[str, Any]]) -> dict:
    """把模型这一轮的"要调工具"原样记回 messages。

    ⚠️ `content` 即使是空的也要带上：OpenAI 兼容接口对"
       有 tool_calls 但没有 content 字段"的处理不一致，
       给个空字符串最稳。
    """
    return {
        "role": "assistant",
        "content": _content_of(message),
        "tool_calls": tool_calls,
    }


def _content_of(message: dict[str, Any]) -> str:
    """取模型回复的正文，兼容它给 None / 非字符串的情况。"""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _dump(payload: Any) -> str:
    """工具结果 → JSON 字符串。

    工具返回里可能有 date / Decimal 这类 json 不认识的类型，
    用 `default=str` 兜底——总比因为一个日期把整轮对话炸掉好。
    """
    return json.dumps(payload, ensure_ascii=False, default=str)


def _summarize(name: str, result: dict[str, Any]) -> str:
    """把工具结果压成一句话，给前端展示"它查到了什么"。

    刻意做得粗略：这是给用户看的**过程提示**，不是数据本身。
    数据在模型那里，用户要看细节可以去冰箱页、菜单页。
    """
    if not result.get("ok"):
        return str(result.get("error") or "查询失败")

    for key, unit in (("items", "条食材"), ("recipes", "道菜"), ("categories", "个分类")):
        if key in result:
            count = result.get("count", 0)
            return f"{count} {unit}" + ("（已截断）" if result.get("truncated") else "")

    if result.get("found") is False:
        return "权威数据源里没有"
    if "energy_kcal_per_100g" in result:
        return f"{result.get('matched_name')} · {result.get('energy_kcal_per_100g')} kcal/100g"

    return "完成"
