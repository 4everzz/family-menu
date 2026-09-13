"""家庭组业务规则。

这一层放"规则"，不放数据库操作（在 Repository），也不放参数解析（在接口层）。
所有"能不能做"的判断都写在这里，接口层只负责把它们翻译成返回结果。

一条安全原则：
    "是不是这个家庭组的成员"必须由后端查数据库来判断。
    前端把按钮藏起来只是体验优化，别人完全可以绕开界面直接调接口。
"""

import logging
import secrets

from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError
from app.models.space import ROLE_ADMIN, ROLE_MEMBER, Space, SpaceMember
from app.models.user import User
from app.repositories.space_repo import SpaceRepository

logger = logging.getLogger(__name__)

# 邀请码字符集：去掉了 I、L、O、0、1 这些容易看错的字符。
# 家人之间常常是口头念或手抄邀请码，少一个歧义就少一次"怎么加不进去"。
INVITE_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
INVITE_CODE_LENGTH = 8
MAX_INVITE_CODE_RETRY = 5


class SpaceService:
    """家庭组服务。"""

    def __init__(self, repo: SpaceRepository) -> None:
        self.repo = repo

    # ==================== 写操作 ====================

    async def create_space(self, user: User, name: str) -> tuple[Space, str, int]:
        """创建家庭组，创建者自动成为管理员。

        返回：(家庭组, 我的角色, 成员数)
        """
        cleaned_name = name.strip()
        if not cleaned_name:
            raise BusinessError("家庭组名称不能为空")

        invite_code = await self._generate_unique_invite_code()
        space = await self.repo.create(name=cleaned_name, owner_id=user.id, invite_code=invite_code)

        # 创建者就是管理员：管理员身份只用于管理动作（比如把人移出家庭组），
        # 业务上不区分谁做菜、谁买菜这类分工。
        await self.repo.add_member(space_id=space.id, user_id=user.id, role=ROLE_ADMIN)
        logger.info("创建家庭组 | space_id=%s | owner_id=%s", space.id, user.id)
        return space, ROLE_ADMIN, 1

    async def join_space(self, user: User, invite_code: str) -> tuple[Space, str, int]:
        """用邀请码加入家庭组。

        返回：(家庭组, 我的角色, 成员数)
        """
        space = await self.repo.get_by_invite_code(invite_code)
        if space is None:
            # 对外统一说"邀请码无效"，不区分"不存在"和其他情况——
            # 说得越细，越方便别人拿脚本去猜有效的邀请码。
            raise NotFoundError("邀请码无效，请确认后重试")

        existing = await self.repo.get_member(space.id, user.id)
        if existing is not None:
            raise BusinessError("你已经在这个家庭组里了")

        await self.repo.add_member(space_id=space.id, user_id=user.id, role=ROLE_MEMBER)
        member_count = await self.repo.count_members(space.id)
        logger.info("加入家庭组 | space_id=%s | user_id=%s", space.id, user.id)
        return space, ROLE_MEMBER, member_count

    # ==================== 读操作 ====================

    async def list_my_spaces(self, user: User) -> list[tuple[Space, str, int]]:
        """我加入的全部家庭组，附我的角色和成员数。"""
        return await self.repo.list_by_user(user.id)

    async def get_space_detail(self, user: User, space_id: int) -> tuple[Space, str, int]:
        """查看某个家庭组详情（需要是该组成员）。"""
        space, member = await self._ensure_member(space_id, user.id)
        member_count = await self.repo.count_members(space_id)
        return space, member.role, member_count

    async def list_members(self, user: User, space_id: int) -> list[tuple[SpaceMember, User]]:
        """查看家庭成员列表（需要是该组成员）。"""
        await self._ensure_member(space_id, user.id)
        return await self.repo.list_members(space_id)

    # ==================== 内部工具 ====================

    async def _ensure_member(self, space_id: int, user_id: int) -> tuple[Space, SpaceMember]:
        """校验"当前用户是該家庭成员"，不是就拒绝。

        这是所有家庭组相关接口的公共前置检查，统一放在这里，
        避免某个新接口忘了加校验而把别人家的数据读出去。
        """
        space = await self.repo.get_by_id(space_id)
        if space is None:
            raise NotFoundError("家庭组不存在")

        member = await self.repo.get_member(space_id, user_id)
        if member is None:
            raise ForbiddenError("你不是这个家庭组的成员")

        return space, member

    async def _generate_unique_invite_code(self) -> str:
        """生成一个当前没被占用的邀请码。

        邀请码长度 8、字符集 31 个字符，组合数约 8.5×10^11，
        随机猜中的概率极低。这里仍做一次查重，冲突就重来。
        """
        for _ in range(MAX_INVITE_CODE_RETRY):
            code = "".join(secrets.choice(INVITE_CODE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))
            if await self.repo.get_by_invite_code(code) is None:
                return code

        # 连续多次都撞上，说明邀请码空间或随机源出了问题，宁可报错也不要写入重复值
        logger.error("邀请码生成连续冲突 %s 次", MAX_INVITE_CODE_RETRY)
        raise BusinessError("邀请码生成失败，请稍后重试", http_status=500)
