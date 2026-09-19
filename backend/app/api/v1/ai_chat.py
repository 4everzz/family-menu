"""AI 对话接口。

接口层保持"薄"：只收参数、调 Service、返回结果。规则都在 Service 层。

⭐ 模型**不写业务数据**。
   模型只产出"动作草案"（actions），用户在确认卡片上点「记下」之后，
   前端才去调**已有的** /users/me/calorie-logs 写入。
   好处是 AI 没有直接改数据的能力——它抽错了，最多是卡片显示错，不会脏库。
   （对话消息本身存进 ai_chat_messages，那是对话的记录，不是业务数据。）

⭐ 身份只从令牌解析（CurrentUser），**不接受客户端传 user_id**。
   前端把按钮藏起来不是安全边界，别人可以直接调接口。

⭐ 上下文（history）由后端自己从库里取，前端不传。
   传的话就等于让前端负责记忆——刷新/换设备上下文就断了。
"""

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.response import success
from app.repositories.ai_chat_repo import AiChatRepository
from app.schemas.ai_chat import AiChatMessageResponse, AiChatRequest
from app.services.ai_chat_service import AiChatService

router = APIRouter(tags=["AI对话"])


def _build_service(session: AsyncSession) -> AiChatService:
    """装配：对话服务只需要历史仓储（模型调用走配置，不依赖注入）。"""
    return AiChatService(AiChatRepository(session))


@router.post("/ai/chat", summary="AI 对话（用一句话记账）")
async def ai_chat(
    payload: AiChatRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """处理一轮对话：自动带上最近的上下文，并把这一轮存进历史。

    返回自然语言回复 + 待用户确认的动作草案。
    """
    result = await _build_service(session).chat(current_user.id, payload)
    await session.commit()  # 落库这一轮的两条消息
    return success(result.model_dump())


@router.get("/ai/chat/messages", summary="对话历史")
async def list_ai_messages(
    current_user: CurrentUser,
    session: DbSession,
    limit: int = Query(default=50, ge=1, le=100, description="最多取多少条"),
) -> dict:
    """取当前用户的最近对话（时间正序），对话页进页面时回放。

    只回文本气泡，不带动作卡片——理由见 AiChatMessageResponse 的注释。
    """
    messages = await _build_service(session).list_messages(current_user.id, limit)
    return success([AiChatMessageResponse.model_validate(m).model_dump() for m in messages])


@router.delete("/ai/chat/messages", summary="清空对话（开始新对话）")
async def clear_ai_messages(current_user: CurrentUser, session: DbSession) -> dict:
    """清空当前用户的全部对话历史，上下文从此从头开始。"""
    cleared = await _build_service(session).clear_messages(current_user.id)
    await session.commit()
    return success({"cleared": cleared})
