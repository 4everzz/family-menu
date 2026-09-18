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

        ⚠️ 末尾这次 refresh 不是多余的（2026-09-18 修 bug）：
        updated_at 由数据库生成，**UPDATE 之后这一列会被标记为过期**；
        接口层紧接着 commit、把连接还给连接池，这时再读它就变成
        "在非异步上下文里发 SQL"，直接抛 MissingGreenlet。
        症状很有迷惑性——**只有改已有档案时才 500，新建档案时没事**
        （INSERT 走 RETURNING 会把服务端默认值一起带回来，不会过期）；
        所以"选完性别点保存"会失败，而首次建档却是好的。
        同款坑和同样解法也见 category_repo.update / favorite_repo。
        """
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            self.session.add(profile)
        for key, value in changes.items():
            setattr(profile, key, value)
        await self.session.flush()
        await self.session.refresh(profile)
        return profile
