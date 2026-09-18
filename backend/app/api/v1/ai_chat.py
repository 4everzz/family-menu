"""AI 对话接口。

接口层保持"薄"：只收参数、调 Service、返回结果。规则都在 Service 层。

⭐ 本接口**不写库**。
   模型只产出"动作草案"（actions），用户在确认卡片上点「记下」之后，
   前端才去调**已有的** /users/me/calorie-logs 写入。
   好处是 AI 没有直接改数据的能力——它抽错了，最多是卡片显示错，不会脏库。

⭐ 身份只从令牌解析（CurrentUser），**不接受客户端传 user_id**。
   前端把按钮藏起来不是安全边界，别人可以直接调接口。

本轮不需要 DbSession：不查库也不写库。将来做"推荐吃什么"时要按家庭组检索，
那时才加 space_id 的成员校验（而且必须在服务端校验，不能信客户端传的值）。
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.response import success
from app.schemas.ai_chat import AiChatRequest
from app.services.ai_chat_service import AiChatService

router = APIRouter(tags=["AI对话"])


@router.post("/ai/chat", summary="AI 对话（用一句话记账）")
async def ai_chat(payload: AiChatRequest, current_user: CurrentUser) -> dict:
    """处理一轮对话，返回自然语言回复 + 待用户确认的动作草案。

    `current_user` 在本轮只起鉴权作用（拿到它就说明已登录），不参与业务。
    """
    result = await AiChatService().chat(payload)
    return success(result.model_dump())
