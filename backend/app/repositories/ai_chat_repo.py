"""AI 对话历史的数据访问。

约定同其它 repository：只管查和存，不写业务规则，也不调用 commit。
所有查询都带 user_id + space_id 过滤——家庭之间的对话不能串。

⚠️ 本表没有"UPDATE 后再读"的路径（只有插入、查询、整段删除），
所以不需要 category_repo/favorite_repo 那样的 flush 后 refresh；
但如果将来加编辑消息之类的操作，记得补上（见 user_profile_repo 的注释）。
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_chat import ROLE_ASSISTANT, ROLE_USER, AiChatMessage


class AiChatRepository:
    """AI 对话消息的查询与写入。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_user_message(
        self, user_id: int, content: str, space_id: int | None = None
    ) -> AiChatMessage:
        """记下用户这一句。"""
        message = AiChatMessage(
            user_id=user_id, space_id=space_id, role=ROLE_USER, content=content
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def add_assistant_message(
        self,
        user_id: int,
        content: str,
        actions: list[dict] | None = None,
        space_id: int | None = None,
    ) -> AiChatMessage:
        """记下 AI 这一轮的回复（动作草案原样存，仅备查）。"""
        message = AiChatMessage(
            user_id=user_id,
            space_id=space_id,
            role=ROLE_ASSISTANT,
            content=content,
            actions=actions,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_recent(
        self, user_id: int, limit: int, space_id: int | None = None
    ) -> list[AiChatMessage]:
        """取某用户某个上下文最近 `limit` 条消息，按时间正序返回。

        实现说明：先按 created_at 倒序取 limit 条，再在 Python 侧反转。
        数据库侧不需要"正序取最后 N 条"这种更绕的写法。
        """
        stmt = select(AiChatMessage).where(AiChatMessage.user_id == user_id)
        if space_id is None:
            stmt = stmt.where(AiChatMessage.space_id.is_(None))
        else:
            stmt = stmt.where(AiChatMessage.space_id == space_id)
        stmt = stmt.order_by(AiChatMessage.created_at.desc(), AiChatMessage.id.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(reversed(result.scalars().all()))

    async def delete_all(self, user_id: int, space_id: int | None = None) -> int:
        """清空某用户某个上下文的全部对话，返回删掉的条数。"""
        stmt = delete(AiChatMessage).where(AiChatMessage.user_id == user_id)
        if space_id is None:
            stmt = stmt.where(AiChatMessage.space_id.is_(None))
        else:
            stmt = stmt.where(AiChatMessage.space_id == space_id)
        result = await self.session.execute(stmt)
        return result.rowcount or 0
