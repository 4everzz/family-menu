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

    # ---- 额度用量：同一个"我参加了几个家"，要按两种口径分开数 ----
    #
    # 为什么不能只数成员表？
    #   因为创建人也会在成员表里有一行，只数成员表会把"自己建的家"
    #   也算成"加入的"，额度就平白少一个位置。
    #   所以"我创建的"看 owner_id，"我加入的"= 成员表里那些 owner 不是我的。

    async def count_owned_by_user(self, user_id: int) -> int:
        """统计这个用户**创建**的家庭组数量（额度里的"我创建的"）。"""
        stmt = select(func.count(Space.id)).where(Space.owner_id == user_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def count_joined_by_user(self, user_id: int) -> int:
        """统计这个用户**以成员身份加入**的家庭组数量（不含自己创建的）。"""
        stmt = (
            select(func.count(SpaceMember.id))
            .join(Space, Space.id == SpaceMember.space_id)
            .where(SpaceMember.user_id == user_id, Space.owner_id != user_id)
        )
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

    async def delete_member(self, member: SpaceMember) -> None:
        """删除一条成员记录。

        「退出家庭组」和「移除成员」共用这一个方法：
        它们在数据库层面做的事完全一样，区别只在"谁有权删谁"——
        那属于业务规则，放在 Service 层判断。
        """
        await self.session.delete(member)
        await self.session.flush()

    async def delete_space(self, space: Space) -> None:
        """删除家庭组（解散）。

        成员记录、菜谱、菜谱分类都会跟着被清理——**不是这里逐张表去删的**，
        而是数据库上的外键规则（ON DELETE CASCADE）自动完成的。
        这样写的好处：将来再加"属于家庭组"的新表，只要外键写对了，
        解散时就会一起清理，不会留下孤儿数据。
        （注意菜谱表的 created_by 指向 users 用的是 RESTRICT，
         那是防"删用户把全家的菜带走"，和这里删家庭组不冲突。）
        """
        await self.session.delete(space)
        await self.session.flush()
