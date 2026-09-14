"""登录方式表（user_identities）的数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_identity import UserIdentity


class UserIdentityRepository:
    """登录方式表的查询与写入。

    与 UserRepository 同一套约定：只 flush，不 commit，事务边界交给 Service 层。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_external_id(self, provider: str, external_id: str) -> UserIdentity | None:
        """按"来源 + 该来源下的标识"查一条绑定。

        这是第三方登录的核心查询：拿微信给的 openid，反查这个人在我们这边是哪个账号。
        两个条件必须一起用——单看 external_id 是不够的，
        不同平台完全可能给出相同的标识串，那样就会串号。
        """
        result = await self.session.execute(
            select(UserIdentity).where(
                UserIdentity.provider == provider,
                UserIdentity.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        provider: str,
        external_id: str,
        unionid: str | None = None,
    ) -> UserIdentity:
        """新增一条登录方式绑定。"""
        identity = UserIdentity(
            user_id=user_id,
            provider=provider,
            external_id=external_id,
            unionid=unionid,
        )
        self.session.add(identity)
        await self.session.flush()
        return identity
