"""AI 对话历史（私有域：挂在 user_id 上）。

为什么对话历史要落库：
    对话能成立靠的是上下文——"再加一碗"这种省略句，全靠前几轮才看得懂。
    历史只存在前端页面内存里的话，关掉页面就丢，用户每次进来都要从头说一遍。
    落库之后上下文由**后端**自己取（见 ai_chat_service），前端连 history 都不用传了。

为什么只建一张 messages 表、不建"会话"表：
    v1 的「新对话」= 清空这个用户的全部消息，点一下就有干净的上下文，够用了。
    真要做多条并行会话时再加 conversations 表，把现有数据挂过去也简单——
    不要为一个还没出现的需求先建两张表。

和"AI 不写库"的边界怎么协调：
    消息本身是对话的**记录**，不是业务数据——存它不影响"AI 没有直接改数据的能力"
    这条规则（热量记录的写入仍然只发生在用户点「记下」之后，走已有接口）。
    actions 原样存下来只是为了备查/回放，**重新进页面时不回放确认卡片**：
    卡片上的「已记下」是前端本地状态，回放会让用户对着已记过的菜再点一次「记下」→ 重复记录。
"""

from sqlalchemy import BigInteger, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# 角色取值（对话里只有这两个）
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"


class AiChatMessage(Base, TimestampMixin):
    """一条 AI 对话消息。用户一句、AI 一句，各占一行，按时间正序读。"""

    __tablename__ = "ai_chat_messages"
    __table_args__ = (
        # 高频查询只有一种："取某用户最近 N 条"——复合索引正好覆盖
        Index("ix_ai_chat_messages_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="消息 ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="谁的对话。私有域：用户注销时一并清理",
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="角色：user 用户 / assistant AI"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息文本")
    # 用 JSON 而不是 JSONB：和 recipes.spice_options 保持同一套写法，本表也不需要按它查询
    actions: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="assistant 消息附带的动作草案（原样存，仅备查；user 消息为 null）"
    )
