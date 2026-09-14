"""家庭组额度：一个人能"建"几个、能"加"几个。

为什么把额度单独抽成一个文件，而不是在 SpaceService 里写两个常量？
    因为额度**将来会因人而异**——用户已经明确说了以后要开会员，会员加次数。
    如果直接写死 `if owned_count >= 2`，那天要做会员时，
    就得把所有散落的判断一个个找出来改，还一定漏。
    现在所有额度都从 space_quota_for(user) 拿，将来只改这一个函数：
    读一下用户的会员等级、返回更大的数字即可，**调用方一行都不用动**。

这就是"参数不写死"的落点：不是把常量挪个位置，而是把"取额度"这件事收成一个入口。
"""

from dataclasses import dataclass

from app.core.config import settings
from app.models.user import User


@dataclass(frozen=True)
class SpaceQuota:
    """一个用户的家庭组额度。

    frozen=True 让它不可变——额度算出来之后不应该被某个环节顺手改掉，
    否则"校验用的额度"和"界面显示的额度"可能对不上。
    """

    #: 最多能拥有几个（"我创建的"）
    max_owned: int
    #: 最多能加入几个（"我加入的"，不含自己建的）
    max_joined: int


def space_quota_for(user: User) -> SpaceQuota:
    """返回这个用户的家庭组额度。

    ---- 目前：所有人一视同仁，直接取配置里的默认值 ----

    ---- 将来接会员时，只需要动这个函数，例如： ----
        tier = membership_tier_of(user)   # free / pro / vip
        return QUOTA_BY_TIER[tier]
        # 或者：base = settings.max_owned_spaces; return SpaceQuota(base + user.bonus_owned, ...)

    注意入参是 user 而不是 user_id：
    将来看会员等级大概率需要读用户身上的字段（或关联的会员表），
    现在就把它当"按人给额度"的接口，签名不用再改。
    """
    return SpaceQuota(
        max_owned=settings.max_owned_spaces,
        max_joined=settings.max_joined_spaces,
    )
