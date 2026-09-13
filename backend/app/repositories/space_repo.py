"""家庭组表的数据访问。

约定同 user_repo：这一层只管查和存，不写业务规则，也不调用 commit。
事务边界由 Service 或接口层决定。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.space import Space, SpaceMember
from app.models.user import User


class SpaceRepository:
    """家庭组与成员表的查询与写入。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ==================== 家庭组 ====================

    async def get_by_id(self, space_id: int) -> Space | None:
        """按主键查家庭组。"""
        return await self.session.get(Space, space_id)

    async def get_by_invite_code(self, invite_code: str) -> Space | None:
        """按邀请码查家庭组。

        邀请码统一转成大写后查询，这样用户输入小写也能加入，少一次挫败。
        """
        stmt = select(Space).where(Space.invite_code == invite_code.strip().upper())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, name: str, owner_id: int, invite_code: str) -> Space:
        """新建家庭组。返回的对象已带数据库生成的自增 ID。"""
        space = Space(name=name, owner_id=owner_id, invite_code=invite_code)
        self.session.add(space)
        await self.session.flush()
        return space

    async def list_by_user(self, user_id: int) -> list[tuple[Space, str, int]]:
        """查询某个用户加入的全部家庭组。

        返回 (家庭组, 我的角色, 成员数) 三元组。
        成员数用子查询一次算出来，避免在循环里逐个家庭组再查一次
        （那就是典型的 N+1 查询问题：10 个家庭组会发 11 条 SQL）。
        """
        member_count = (
            select(SpaceMember.space_id, func.count(SpaceMember.id).label("member_count"))
            .group_by(SpaceMember.space_id)
            .subquery()
        )

        stmt = (
            select(Space, SpaceMember.role, func.coalesce(member_count.c.member_count, 0))
            .join(SpaceMember, SpaceMember.space_id == Space.id)
            .outerjoin(member_count, member_count.c.space_id == Space.id)
            .where(SpaceMember.user_id == user_id)
            .order_by(Space.id)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1], int(row[2])) for row in result.all()]

    # ==================== 成员 ====================

    async def get_member(self, space_id: int, user_id: int) -> SpaceMember | None:
        """查询某用户在某家庭组的成员记录。返回 None 表示不是该组成员。"""
        stmt = select(SpaceMember).where(
            SpaceMember.space_id == space_id,
            SpaceMember.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_member(self, space_id: int, user_id: int, role: str) -> SpaceMember:
        """添加成员。"""
        member = SpaceMember(space_id=space_id, user_id=user_id, role=role)
        self.session.add(member)
        await self.session.flush()
        return member

    async def count_members(self, space_id: int) -> int:
        """统计家庭组当前成员数。"""
        stmt = select(func.count(SpaceMember.id)).where(SpaceMember.space_id == space_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def list_members(self, space_id: int) -> list[tuple[SpaceMember, User]]:
        """列出家庭组的全部成员及其用户信息。

        这里用一次 join 把成员和用户信息一起取回来，
        而不是先查成员再逐个查用户（同样是避免 N+1）。
        """
        stmt = (
            select(SpaceMember, User)
            .join(User, User.id == SpaceMember.user_id)
            .where(SpaceMember.space_id == space_id)
            .order_by(SpaceMember.id)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]
