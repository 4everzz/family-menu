"""用户表的数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """用户表的查询与写入。

    约定：这一层不调用 commit，只 flush（把语句发给数据库拿到自增 ID）。
    事务边界由 Service 层决定，这样一个业务动作涉及的多次写入要么全成功、要么全回滚。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        """按主键查询。session.get 会优先走一级缓存，比手写 select 更省一次查询。"""
        return await self.session.get(User, user_id)

    async def get_by_openid(self, openid: str) -> User | None:
        """按微信 openid 查询。"""
        result = await self.session.execute(select(User).where(User.openid == openid))
        return result.scalar_one_or_none()

    async def create(
        self,
        openid: str,
        nickname: str = "微信用户",
        avatar_url: str | None = None,
    ) -> User:
        """新建用户。返回的对象已经带上数据库生成的自增 ID。"""
        user = User(openid=openid, nickname=nickname, avatar_url=avatar_url)
        self.session.add(user)
        await self.session.flush()
        return user
