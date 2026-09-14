"""个人资料的业务规则。

为什么要单独一个 Service，而不是在接口里直接改两个字段？
    因为"改昵称"这件事看着简单，实际有几条规则要守：
      · 昵称不能是空白（数据库那列是 NOT NULL，存个空串进去界面会空一块）；
      · 昵称有长度上限；
      · 头像只接受本站上传接口产出的相对路径，不能让任意 URL 写进来；
      · 这些规则将来一旦要加（比如昵称查重、敏感词），只改这一处，所有入口都跟着变。

接口层（app/api/v1/users.py）只负责收参数、调这里、返回结果。
"""

from app.core.exceptions import BusinessError
from app.models.user import User
from app.repositories.user_repo import UserRepository

# 头像只接受本站上传接口产出的相对路径。
# 为什么不让直接填任意 URL？这个字段最终会进 <image src>，
# 放任外部地址等于把"页面上显示什么图"的控制权交给别人；
# 而上传接口本身已经做了扩展名白名单 + 文件头魔数 + 大小三重校验，走它更安全。
AVATAR_URL_PREFIX = "/uploads/"

# 与 schemas/user.py 的 UserUpdateRequest 保持一致
MAX_NICKNAME_LENGTH = 64
MAX_AVATAR_URL_LENGTH = 512


class UserService:
    """个人资料相关业务。"""

    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo

    async def update_profile(self, user: User, changes: dict) -> User:
        """按传入的字段更新个人资料。

        参数 changes 只包含请求体里**真正出现过**的键（接口层用 exclude_unset 得到），
        所以这里不需要猜用户到底想改哪个字段——
        没出现的键保持原值，出现了但值为 null 的按下面各自的语义处理。
        """
        if not changes:
            # 传了个空对象来说明"什么都不改"，多半是前端写错了，明确报出来比静默成功好
            raise BusinessError("没有需要修改的内容")

        if "nickname" in changes:
            user.nickname = self._clean_nickname(changes["nickname"])

        if "avatar_url" in changes:
            user.avatar_url = self._clean_avatar_url(changes["avatar_url"])

        return await self.repo.save(user)

    @staticmethod
    def _clean_nickname(value: str | None) -> str:
        """校验并规整昵称。"""
        if value is None:
            # 数据库那一列是 NOT NULL。显式传 null 等于"把昵称删掉"，
            # 这个操作没有意义（界面上总得有个名字），直接拒绝。
            raise BusinessError("昵称不能为空")

        cleaned = value.strip()
        if not cleaned:
            raise BusinessError("昵称不能为空")

        if len(cleaned) > MAX_NICKNAME_LENGTH:
            raise BusinessError(f"昵称最多 {MAX_NICKNAME_LENGTH} 个字")

        return cleaned

    @staticmethod
    def _clean_avatar_url(value: str | None) -> str | None:
        """校验头像地址。

        返回 None 表示"恢复默认头像"，这是允许的：
        用户可能就想把自定义头像撤掉，前端拿到 null 会显示默认占位图。
        """
        if value is None:
            return None

        cleaned = value.strip()
        if not cleaned:
            return None

        if len(cleaned) > MAX_AVATAR_URL_LENGTH:
            raise BusinessError("头像地址过长")

        if not cleaned.startswith(AVATAR_URL_PREFIX):
            raise BusinessError("头像地址不合法，请先通过上传接口上传图片")

        return cleaned
