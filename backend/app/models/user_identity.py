"""登录方式表（身份绑定）。

把"这个人是谁"（users）和"这个人用什么登录"（本表）拆开。

为什么要独立成表，而不是往 users 加列？
    1. 一种登录方式是一行数据，不是一列。加微信 App / QQ / 手机号时只插数据，不改表结构；
    2. 唯一性约束能表达得更准确：真正要保证唯一的是"某个平台的某个标识只能绑一个账号"，
       也就是 (provider, external_id) 唯一——这个约束在"每种方式一列"的表里写不出来；
    3. 改造前 users.openid 是 NOT NULL 且唯一，自建账号根本没有 openid，注册时插不进去。
       把第三方身份挪到本表，users 才能真正只描述"人"。

附带的好处：将来如果同一个人既在小程序登录又在 App 登录，
两个 openid 可以各占一行、指向同一个 user_id，天然就是"绑定"关系。
"""

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# ---------- 登录来源 ----------
# 目前只有微信小程序：它的静默登录免费可用，不需要企业认证。
# 微信 App 端登录、QQ 登录都需要微信开放平台/QQ互联的企业认证（300 元/年，个人申请不了），
# 所以暂时不做；将来拿到资质后在这里加常量、业务代码不用动结构。
PROVIDER_WX_MP = "wx_mp"  # 微信小程序


class UserIdentity(Base, TimestampMixin):
    """一条"某用户用某种方式登录"的绑定记录。"""

    __tablename__ = "user_identities"
    __table_args__ = (
        # 同一个平台的同一个标识，只能绑到一个账号上。
        # 这条约束必须放在数据库层：并发注册时"先查后插"是拦不住的，
        # 两个请求可能同时查到"没占用"，然后各插一行。
        UniqueConstraint("provider", "external_id", name="uq_user_identities_provider_external_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户。用户注销时这条绑定跟着删（CASCADE）",
    )
    provider: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="登录来源。目前取值：wx_mp=微信小程序",
    )
    external_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="该平台下识别用户的标识。微信小程序存的是 openid",
    )
    unionid: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="微信 unionid，用于跨应用识别同一个人；未绑定微信开放平台时为空",
    )

    def __repr__(self) -> str:
        """调试用：一眼看出是哪个人、用哪种方式。"""
        return f"<UserIdentity user_id={self.user_id} provider={self.provider!r}>"
