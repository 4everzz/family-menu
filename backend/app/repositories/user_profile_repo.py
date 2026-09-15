"""个人健康档案的数据访问。

约定同其它 repository：只管查和存，不写业务规则，也不调用 commit。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_profile import UserProfile


class UserProfileRepository:
    """健康档案：一人一行，upsert 语义。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_id(self, user_id: int) -> UserProfile | None:
        """按 user_id 取这一行（前端不传 ID，从令牌解析）。"""
        stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, user_id: int, changes: dict) -> UserProfile:
        """存在就更新、不存在就新建，应用 changes 后 flush（不 commit）。

        changes 的键就是模型字段名（gender/height_cm/...），直接 setattr。
        """
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            self.session.add(profile)
        for key, value in changes.items():
            setattr(profile, key, value)
        await self.session.flush()
        return profile
