"""用户表的数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import DEFAULT_NICKNAME, User


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

    async def get_by_username(self, username: str) -> User | None:
        """按登录用户名查询。

        调用方必须传入**已归一化**的用户名（去掉首尾空格 + 转小写），
        否则拿 "Tom" 是查不到库里存成 "tom" 的那一行的。
        归一化统一在请求模型里做（见 app/schemas/auth.py），
        所以调用方拿到的 payload.username 已经是干净的，不需要在这里再处理一遍。
        """
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def create_local_user(self, username: str, password_hash: str) -> User:
        """创建一个"用户名 + 密码"的自建账号。

        昵称**不在注册时收集**（用户要去「我的」页改资料），所以这里统一用默认昵称。
        注册表单每多一个字段，放弃注册的人就多一分——能省则省。

        注意这里**不检查用户名是否重复**：唯一性最终由 users.username 上的唯一索引保证
        （并发场景下"先查后插"是拦不住的）。是否重复的判断与友好提示放在 Service 层，
        数据库抛出的冲突也在 Service 层翻译成人话。
        """
        user = User(
            username=username,
            password_hash=password_hash,
            nickname=DEFAULT_NICKNAME,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def create_wechat_user(self) -> User:
        """创建一个"只有微信身份、没有用户名密码"的用户。

        改造前的老用户就是这种形态：能从小程序登录，但还没有自己的账号密码。
        这条路径不带任何输入，所以昵称用默认值。
        """
        user = User(nickname=DEFAULT_NICKNAME)
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_credentials(
        self,
        user: User,
        *,
        username: str | None,
        password_hash: str | None,
    ) -> User:
        """更新登录凭据。**只写传进来的字段**（None 表示这一项不改）。

        调用方必须传入**已归一化**的用户名，理由同 get_by_username。

        ⚠️ flush 之后必须 refresh：
            `updated_at` 是数据库那边生成的列，flush 只把语句发出去，
            对象上的这个属性还是旧的（甚至触发一次懒加载）。
            紧接着读它就会撞上 MissingGreenlet——这个坑项目里踩过好几次了。
        """
        if username is not None:
            user.username = username
        if password_hash is not None:
            user.password_hash = password_hash
        await self.save(user)
        await self.session.refresh(user)
        return user

    async def save(self, user: User) -> User:
        """把对象上已修改的字段写回数据库。

        为什么需要这个方法？其实 ORM 会自动跟踪对象属性的改动，
        但我们约定"这一层不 commit、只 flush"，把语句及时发给数据库，
        这样唯一约束之类的错误会在业务代码附近的这一行暴露出来，
        而不是拖到接口层 commit 时才炸——那时候堆栈里已经看不出是谁改的。
        """
        self.session.add(user)
        await self.session.flush()
        return user
