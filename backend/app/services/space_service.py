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
from app.repositories.category_repo import CategoryRepository
from app.repositories.space_repo import SpaceRepository
from app.services.space_quota import SpaceQuota, space_quota_for

logger = logging.getLogger(__name__)

# 邀请码字符集：去掉了 I、L、O、0、1 这些容易看错的字符。
# 家人之间常常是口头念或手抄邀请码，少一个歧义就少一次"怎么加不进去"。
INVITE_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
INVITE_CODE_LENGTH = 8
MAX_INVITE_CODE_RETRY = 5


class SpaceService:
    """家庭组服务。"""

    def __init__(self, repo: SpaceRepository, category_repo: CategoryRepository) -> None:
        self.repo = repo
        # 新建家庭组时要一并把这个家的默认菜谱分类准备好，所以这里持有分类表的访问入口。
        #
        # 为什么是"注入一个 Repository"而不是在方法里自己 new 一个？
        # 因为要保证"建家庭组"和"建默认分类"用的是**同一个数据库会话**，
        # 也就是落在同一个事务里。否则第二步失败时会留下一个没有任何分类的家庭组：
        # 用户进去只看到空侧边栏，还以为是自己点错了，实际是数据建了一半。
        self.category_repo = category_repo

    # ==================== 写操作 ====================

    async def create_space(self, user: User, name: str) -> tuple[Space, str, int]:
        """创建家庭组，创建者自动成为管理员。

        返回：(家庭组, 我的角色, 成员数)
        """
        cleaned_name = name.strip()
        if not cleaned_name:
            raise BusinessError("家庭组名称不能为空")

        # 先看额度再看别的：额度是硬性门槛，早点拦住可以少做几次数据库操作
        await self._ensure_can_own(user)

        invite_code = await self._generate_unique_invite_code()
        space = await self.repo.create(name=cleaned_name, owner_id=user.id, invite_code=invite_code)

        # 创建者就是管理员：管理员身份只用于管理动作（比如把人移出家庭组），
        # 业务上不区分谁做菜、谁买菜这类分工。
        await self.repo.add_member(space_id=space.id, user_id=user.id, role=ROLE_ADMIN)

        # 新家自带一套默认分类（凉菜/热菜/汤羹/主食/甜点/饮品），用户之后可以自己增删改。
        # 完全空白的侧边栏会让新用户不知道能干什么，先给一套合理的，不合适他自己改。
        await self.category_repo.create_defaults(space.id)

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

        # 顺序有意：先判"已在组里"，再判额度。
        # 已经是成员的人，提示"已经在这个家庭组里了"比"额度已满"准确得多。
        await self._ensure_can_join(user)

        await self.repo.add_member(space_id=space.id, user_id=user.id, role=ROLE_MEMBER)
        member_count = await self.repo.count_members(space.id)
        logger.info("加入家庭组 | space_id=%s | user_id=%s", space.id, user.id)
        return space, ROLE_MEMBER, member_count

    async def leave_space(self, user: User, space_id: int) -> None:
        """退出家庭组（只能退出自己所在的组）。

        **创建人不允许直接退出，只能解散。**
        为什么这么定：创建人是这个组的归属人，他走了这个组就没人管了。
        而"转让创建人"这个功能我们暂时不做，所以干脆把这条路堵住，
        避免出现"没有创建人的家庭组"这种说不清、后续代码也难处理的状态。
        """
        space, member = await self.ensure_member(space_id, user.id)
        if space.owner_id == user.id:
            raise BusinessError(
                "你是这个家庭的创建人，不能直接退出。要结束它请用「解散家庭组」"
            )

        await self.repo.delete_member(member)
        logger.info("退出家庭组 | space_id=%s | user_id=%s", space_id, user.id)

    async def remove_member(self, user: User, space_id: int, target_user_id: int) -> None:
        """把某个成员移出家庭组（只有创建人能操作）。

        两条容易漏的边界都在这里堵上：
        1. 不能移除自己 —— 创建人想走应该用「解散」，否则同样会留下没有创建人的组；
        2. 不能移除创建人 —— 即便传入的 target 就是创建人自己，也会被第 1 条挡住。
        注意第 2 条不是靠"判断 target 是不是 owner"实现的，而是靠"操作者必须是 owner
        且不能是自己"这两条推出——少写一个判断，就少一处将来会不一致的地方。
        """
        space, _ = await self.ensure_member(space_id, user.id)
        if space.owner_id != user.id:
            raise ForbiddenError("只有这个家庭的创建人才能移除成员")

        if target_user_id == user.id:
            raise BusinessError("不能移除自己。要结束这个家庭请用「解散家庭组」")

        target = await self.repo.get_member(space_id, target_user_id)
        if target is None:
            # 对外说"不在该家庭组里"，而不是"查无此人"——
            # 不泄露"这个用户 ID 是否存在"这种信息
            raise NotFoundError("这个人不在该家庭组里")

        await self.repo.delete_member(target)
        logger.info(
            "移除成员 | space_id=%s | by=%s | target=%s", space_id, user.id, target_user_id
        )

    async def dissolve_space(self, user: User, space_id: int) -> None:
        """解散家庭组（只有创建人能操作）。

        ⚠️ 这是**不可逆**操作：成员关系、菜谱、菜谱分类会一起消失。
        删除动作由数据库的外键级联完成（见 SpaceRepository.delete_space 的说明）。
        前端必须做二次确认，并在确认文案里说清楚会删掉什么。
        """
        space, _ = await self.ensure_member(space_id, user.id)
        if space.owner_id != user.id:
            raise ForbiddenError("只有这个家庭的创建人才能解散它")

        await self.repo.delete_space(space)
        logger.info("解散家庭组 | space_id=%s | owner_id=%s", space_id, user.id)

    # ==================== 读操作 ====================

    async def list_my_spaces(self, user: User) -> list[tuple[Space, str, int]]:
        """我加入的全部家庭组，附我的角色和成员数。"""
        return await self.repo.list_by_user(user.id)

    async def get_space_detail(self, user: User, space_id: int) -> tuple[Space, str, int]:
        """查看某个家庭组详情（需要是该组成员）。"""
        space, member = await self.ensure_member(space_id, user.id)
        member_count = await self.repo.count_members(space_id)
        return space, member.role, member_count

    async def list_members(self, user: User, space_id: int) -> list[tuple[SpaceMember, User]]:
        """查看家庭成员列表（需要是该组成员）。"""
        await self.ensure_member(space_id, user.id)
        return await self.repo.list_members(space_id)

    # ==================== 额度（一个人能建几个 / 加几个） ====================
    #
    # 额度本身不在这里定义——它从 space_quota_for(user) 取（见 services/space_quota.py）。
    # 这样做是为了将来接会员时，只改那一个函数，这里的判断一行都不用动。

    async def get_quota_usage(self, user: User) -> tuple[SpaceQuota, int, int]:
        """返回 (额度, 已创建数, 已加入数)。

        给接口层用来展示"我创建的 1/2、我加入的 0/2"，
        也让前端能在用户点按钮之前就说清"还能不能再建"。
        """
        quota = space_quota_for(user)
        owned = await self.repo.count_owned_by_user(user.id)
        joined = await self.repo.count_joined_by_user(user.id)
        return quota, owned, joined

    async def _ensure_can_own(self, user: User) -> None:
        """建新家之前检查"我创建的"额度，超了就拒绝。

        并发说明：这是"先查数量再插入"，理论上两个人同一瞬间各建一个、
        都通过了检查，就会超出额度一个。家庭场景下概率可以忽略；
        而且这个限制没法用数据库唯一约束表达（它是"每个用户最多 N 行"，
        不是"某一列不能重复"）。将来真要严格，得上行锁或单独的计数表。
        """
        quota = space_quota_for(user)
        owned = await self.repo.count_owned_by_user(user.id)
        if owned >= quota.max_owned:
            raise BusinessError(
                f"您创建的家庭组数量已达上限（{quota.max_owned} 个）。解散一个之后可以再创建。"
            )

    async def _ensure_can_join(self, user: User) -> None:
        """用邀请码加入之前，检查"我加入的"额度，超了就拒绝。

        这一条同时也是"被邀请人已满"的提示：
        加入只有"输邀请码"这一个入口——不管码是自己找的还是家人分享给他的，
        都会走到这里，所以不需要再多一条分支去判断"是不是被邀请的"。
        """
        quota = space_quota_for(user)
        joined = await self.repo.count_joined_by_user(user.id)
        if joined >= quota.max_joined:
            raise BusinessError(
                f"您加入的家庭组数量已达上限（{quota.max_joined} 个）。退出一个之后可以再加入。"
            )

    # ==================== 公共校验（供其他模块复用） ====================

    async def ensure_member(self, space_id: int, user_id: int) -> tuple[Space, SpaceMember]:
        """校验"当前用户是该家庭成员"，不是就拒绝。

        这是所有"以家庭组为单位"的数据（家庭组本身、菜谱、将来的冰箱）的公共前置检查，
        统一放在这里由各模块复用，避免新模块自己再写一遍、写漏一个接口
        就把别人家的数据读出去了。

        为什么方法名不加下划线开头？
            加下划线的约定是"仅内部使用"。这个方法现在要被菜谱等其他模块调用，
            所以改成公开名称，明确它是一种对外承诺的校验入口。
        """
        space = await self.repo.get_by_id(space_id)
        if space is None:
            raise NotFoundError("家庭组不存在")

        member = await self.repo.get_member(space_id, user_id)
        if member is None:
            raise ForbiddenError("你不是这个家庭组的成员")

        return space, member

    async def ensure_owner(self, space_id: int, user_id: int) -> Space:
        """校验"当前用户是这个家庭的创建人"，不是就拒绝。

        用于**改菜单**这类创建人专属动作（菜谱、分类的增删改）。

        为什么单独开一个方法，而不是让每个接口自己去比对 owner_id？
            比对这件事一旦散落在各个接口里，迟早有人漏写一处，
            那一处就成了"普通成员也能改菜单"的破口。
            收口成一个方法，就没有"漏写"的机会。

        注意：这里先调 ensure_member 再比 owner_id。
        顺序有意义——非成员和"是成员但不是创建人"是两种不同的情况，
        前者连"这个家存不存在"都不该知道，所以必须让成员校验先兜住。
        """
        space, _ = await self.ensure_member(space_id, user_id)
        if space.owner_id != user_id:
            raise ForbiddenError("只有这个家庭的创建人才能修改菜单")
        return space

    # ==================== 内部工具 ====================

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
