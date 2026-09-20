"""AI 对话接口的契约。

这一层只定义"前后端之间传什么"，规则都在 services/ai_chat_service.py。

⭐ 为什么响应里要有 actions（结构化草案），而不是让模型直接写库？
   模型从自然语言里抽出来的东西一定会错（菜名听歪、热量估偏）。
   所以拆成两步：模型只负责**提议**，用户点确认卡片才真正写库。
   这条边界让 AI 没有直接改数据的能力——出错了最多是卡片显示错，不会脏库。

⭐ 为什么不在这里写请求校验器？
   空字符串的提示要让用户看得懂（"说点什么吧"），而 Pydantic 给的
   "String should have at least 1 character" 是给开发者看的，
   所以只在服务层做这个判断（见 AiChatService.chat）。
"""

from datetime import datetime

from pydantic import BaseModel, Field

# 单条消息长度上限。用户描述一顿饭不需要更长，也是防止把 prompt 撑爆。
MAX_MESSAGE_LEN = 500


class AiChatTurn(BaseModel):
    """一轮历史消息。

    前端把最近几轮回填进来，让"再加一碗"这类省略句能被理解——没有历史就不叫对话。
    本轮历史只存在前端内存里，后端不落库。
    """

    role: str = Field(..., description="user 或 assistant")
    content: str = Field(..., description="那一轮的原话")


class AiChatRequest(BaseModel):
    """用户这一句（外加一点上下文）。"""

    message: str = Field(..., max_length=MAX_MESSAGE_LEN, description="用户原话")
    history: list[AiChatTurn] = Field(default_factory=list, description="最近若干轮，越旧越靠前")
    # ⚠️ 本轮只透传、不查库：记账是 user 私有域，用不到家庭组。
    # 将来做"推荐吃什么"才需要它，而且届时**必须**在服务端 ensure_member 校验，
    # 绝不能信客户端传过来的这个值。
    space_id: str | None = Field(default=None, description="当前家庭组，预留给未来的菜单推荐")


class ActionDraft(BaseModel):
    """一条"待用户确认"的动作草案。本轮只有一种动作。"""

    kind: str = Field(
        default="create_calorie_log",
        description="动作类型，目前只有 create_calorie_log",
    )
    food_name: str = Field(..., description="食物名")
    # 用户没说重量就是 null —— **不猜、不默认**，前端据此不显示重量
    portion: str | None = Field(default=None, description="份量描述，如 500g；用户没说则为 null")
    calories: float | None = Field(default=None, description="千卡；估算失败时为 null")
    # 用来在卡片上如实标注"这个数是模型估的"，别让用户以为是自己说的那个数
    calories_estimated: bool = Field(
        default=False, description="热量是否为模型估算（用户没给热量时为 true）"
    )
    eaten_at: str = Field(..., description="食用日期 yyyy-mm-dd，只到天（不区分餐段）")
    # ⭐ 可信度分级：这个热量是"查的"还是"猜的"。
    #
    # 为什么要有这个字段？
    #   以前热量全是大模型凭常识估的——同一个红烧肉今天 400、明天 520，
    #   用户既看不出这是估的，也无从判断准不准。
    #   现在接了 MCP 查《中国食物成分表》，热量可能是查出来的。
    #   用 source 如实标出来，前端可以显示"数据来源：中国食物成分表"之类。
    #
    # 取值：
    #   mcp_exact    —— MCP 精确命中（食材名对上了）      → 查的，最可信
    #   mcp_derived  —— MCP 基准 + AI 按烹饪方式修正      → 有依据的推算
    #   llm_estimate —— 纯 AI 估算                        → 猜的（默认值）
    source: str = Field(
        default="llm_estimate",
        description="热量来源：mcp_exact / mcp_derived / llm_estimate",
    )
    #: 命中的食材名（如"红烧肉"→"猪肉"）。让用户知道这个数是"拿什么查的"
    matched_food: str | None = Field(
        default=None, description="MCP 命中的食材名；未命中为 null"
    )


class AiChatResponse(BaseModel):
    """一轮对话的返回。"""

    reply: str = Field(..., description="给用户看的自然语言回复")
    intent: str = Field(default="chat", description="log / chat / recommend（recommend 为预留）")
    actions: list[ActionDraft] = Field(
        default_factory=list, description="结构化草案；闲聊时为空数组"
    )
    mock: bool = Field(default=False, description="是否占位数据（没配识别 Key 时为 true）")


class AiChatMessageResponse(BaseModel):
    """一条历史消息（对话页回放用）。

    ⚠️ 刻意**不带 actions**：确认卡片上的「已记下」是前端本地状态，
    回放历史时若把卡片也渲染出来，用户会对着已经记过的菜再点一次「记下」→ 重复记录。
    所以回放只回文本气泡；要看重不看重，去热量记录页看（那才是真正落了库的东西）。
    （actions 仍存在 ai_chat_messages 表里备查，只是不出这个接口。）
    """

    model_config = {"from_attributes": True}

    id: int = Field(..., description="消息 ID")
    role: str = Field(..., description="user / assistant")
    content: str = Field(..., description="消息文本")
    created_at: datetime = Field(..., description="发送时间")
