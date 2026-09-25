"""AI 对话接口。

接口层保持"薄"：只收参数、调 Service、返回结果。规则都在 Service 层。

⭐ 改造后（2026-09-21）AI 是一个**会用工具的 Agent**：
   它能自己去查冰箱、查菜单、查热量，所以响应里多了 `steps`
   （本轮调了哪些工具、各自什么结果）。**但它依然不写业务数据。**

⭐ 模型**不写业务数据**。
   模型只产出"动作草案"（actions），用户在确认卡片上点「记下」之后，
   前端才去调**已有的** /users/me/calorie-logs 写入。
   好处是 AI 没有直接改数据的能力——它抽错了，最多是卡片显示错，不会脏库。
   工具清单里也**一个写操作都没有**，这条边界是一致的。
   （对话消息本身存进 ai_chat_messages，那是对话的记录，不是业务数据。）

⭐ 身份只从令牌解析（CurrentUser），**不接受客户端传 user_id**。
   前端把按钮藏起来不是安全边界，别人可以直接调接口。
   同理，`space_id` 是客户端传的，服务端**必须**再过一次 ensure_member。

⭐ 上下文（history）由后端自己从库里取，前端不传。
   传的话就等于让前端负责记忆——刷新/换设备上下文就断了。
"""

import json
import logging

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.response import success
from app.repositories.ai_chat_repo import AiChatRepository
from app.schemas.ai_chat import AiChatMessageResponse, AiChatRequest
from app.services.ai_chat_service import AiChatService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI对话"])


def _build_service(session: AsyncSession) -> AiChatService:
    """装配：对话服务要历史仓储 + 数据库会话。

    ⚠️ 为什么现在要 session 了？
       改造后 AI 是个会用工具的 Agent，工具要查冰箱、查菜单——
       那些数据在库里。改造前不需要（那时 AI 只做"从一句话抽字段"，
       碰不到业务数据）。
    """
    return AiChatService(AiChatRepository(session), session)


@router.post("/ai/chat", summary="AI 对话（记账 + 查冰箱/菜单推荐）")
async def ai_chat(
    payload: AiChatRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """处理一轮对话：自动带上最近的上下文，并把这一轮存进历史。

    返回自然语言回复 + 待用户确认的动作草案 + 本轮调用了哪些工具。
    """
    # ⚠️ 传整个 User 对象而不是 user_id：Agent 的工具要拿它去过 ensure_member
    #    （不能只凭一个 ID——那样工具层就得自己再查一次用户，等于两份实现）。
    result = await _build_service(session).chat(current_user, payload)
    await session.commit()  # 落库这一轮的两条消息
    return success(result.model_dump())


def _sse(event: str, data: dict) -> str:
    """把一个事件编成一条 SSE 帧。

    SSE 的帧边界是**空行**（\n\n）；json.dumps 不会产出真实换行
    （字符串里的换行会被转义成 \\n），所以每帧必然完整落在两行以内，
    前端按空行切帧永远不会切坏。

    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/ai/chat/stream", summary="AI 对话（SSE 流式：工具步骤实时推，最后给整包）")
async def ai_chat_stream(
    payload: AiChatRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> StreamingResponse:
    """流式版 /ai/chat，事件序列：`start` → `step`* → `message` → `done`（失败时 `error`）。

    ⭐ 为什么步骤要走流：一轮 Agent 最多 4 次串行模型调用，前后 10 秒起步；
       "查冰箱 · 4 条食材"在**发生时**就推到界面上，
       等待从黑盒变成看得见的进度。总时长没变，感知完全不同。

    ⚠️ 业务错误走 `event: error` 而不是 HTTP 4xx/5xx：
       流式响应的 HTTP 头在第一个字节前就必须发出（那时还不知道业务上会不会失败），
       前端按事件类型区分成功与失败。

    ⚠️ 会话在流式期间保持可用：FastAPI 的 yield 依赖在**响应（含流式体）完整发完
       之后**才执行收尾（0.106+ 行为），所以生成器结束后可以照常 commit。
    """
    service = _build_service(session)

    async def gen():
        async for event, data in service.chat_stream(current_user, payload):
            yield _sse(event, data)
        try:
            await session.commit()  # 落库这一轮的两条消息（与非流式路径一致）
        except Exception:
            # 回复已经发出去了，落库失败不能假装能补救——留下日志供排查
            logger.exception("流式对话落库失败（回复已发出）")

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # 关掉反向代理的响应缓冲（上线挂 nginx 后有用；本地直连无感）
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/ai/chat/messages", summary="对话历史")
async def list_ai_messages(
    current_user: CurrentUser,
    session: DbSession,
    limit: int = Query(default=50, ge=1, le=100, description="最多取多少条"),
    space_id: int | None = Query(default=None, description="家庭组 ID；为空表示个人聊天"),
) -> dict:
    """取当前用户当前家庭的最近对话（时间正序），对话页进页面时回放。

    只回文本气泡，不带动作卡片——理由见 AiChatMessageResponse 的注释。
    """
    service = _build_service(session)
    resolved_space_id = await service._resolve_space_id(current_user, space_id)
    messages = await service.list_messages(current_user.id, limit, resolved_space_id)
    return success([AiChatMessageResponse.model_validate(m).model_dump() for m in messages])


@router.delete("/ai/chat/messages", summary="清空对话（开始新对话）")
async def clear_ai_messages(
    current_user: CurrentUser,
    session: DbSession,
    space_id: int | None = Query(default=None, description="家庭组 ID；为空表示个人聊天"),
) -> dict:
    """清空当前用户当前家庭的对话历史，上下文从此从头开始。"""
    service = _build_service(session)
    resolved_space_id = await service._resolve_space_id(current_user, space_id)
    cleared = await service.clear_messages(current_user.id, resolved_space_id)
    await session.commit()
    return success({"cleared": cleared})
