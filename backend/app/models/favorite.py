"""个人收藏相关表。

这两张表属于**个人私有域**（挂在 user_id 上），和家庭共享域（space_id）刻意分开：
"我觉得这道菜好"是私人的事——同一个家里的两个人，各自收藏各自的，互不影响。
这和"菜谱、分类挂在 space_id 上、全家共享"是两条平行的线，见 models/recipe.py 的说明。

关于「默认收藏夹」——**它不是一行数据，而是一个状态**：
    favorite.partition_id 为 NULL，就代表这道菜躺在默认收藏夹里。
    为什么不真的建一行"默认收藏夹"记录？
        不建，它就永远不会出现"被删了 / 被改名了 / 不存在"这三种问题，
        界面上它也天然永远存在，不需要写任何保护逻辑。
        （如果建了行，就得到处防着"有人把它删了"，防不胜防。）
    分区上限只数自定义的，NULL 不占额度。

删除规则（ondelete）都用 CASCADE：
    用户注销、菜谱被删（例如家庭组解散）、分区被删，收藏都应该跟着消失，
    留着只会变成"指向不存在的东西"的悬空数据。
    其中"删分区"在应用层会**先把里面的收藏挪回默认收藏夹**（更友好，收藏不丢），
    CASCADE 是最后的兜底。
"""

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# 自定义分区名字的最大长度。默认收藏夹不占这个限制——它根本不是一行数据
MAX_PARTITION_NAME_LENGTH = 16


class FavoritePartition(Base, TimestampMixin):
    """收藏分区：用户自定义的"文件夹"。

    只有自定义分区才落库；默认收藏夹是 NULL 状态，不在这里。
    """

    __tablename__ = "favorite_partitions"
    __table_args__ = (
        # 同一个人不允许两个同名分区（"想吃"建两次没有意义，只会困惑）
        UniqueConstraint("user_id", "name", name="uq_favorite_partitions_user_name"),
        # 列表接口永远按 user_id 查、按 sort_order 排，复合索引正好覆盖
        Index("ix_favorite_partitions_user_sort", "user_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="分区 ID",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属用户。分区是纯私有的，用户注销时随之清理",
    )
    name: Mapped[str] = mapped_column(
        String(MAX_PARTITION_NAME_LENGTH),
        nullable=False,
        comment="分区名，例如「想吃」「孩子爱吃」，同一用户内不可重名",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="显示顺序，数字小的在前。新建的排在最后",
    )

    def __repr__(self) -> str:
        """调试时能看到关键信息。"""
        return f"<FavoritePartition id={self.id} user={self.user_id} name={self.name!r}>"


class RecipeFavorite(Base, TimestampMixin):
    """一条收藏记录：某用户把某道菜放进了某个分区（partition_id 为 NULL 即默认收藏夹）。

    为什么用 (user_id, recipe_id) 唯一约束而不是允许重复收藏？
        收藏是个开关，不是计数器。同一道菜收藏两次没有意义，
        而且没有唯一约束的话，"取消收藏"就得删掉不确定的多少行。
        有了约束，收藏/取消都是一次精确的单行操作。
    """

    __tablename__ = "recipe_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "recipe_id", name="uq_recipe_favorites_user_recipe"),
        Index("ix_recipe_favorites_user_partition", "user_id", "partition_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="收藏记录 ID",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="谁收藏的。私有域：只跟着 user_id 走",
    )
    recipe_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        comment="被收藏的菜谱。菜谱没了（如家庭组解散），收藏随之消失",
    )
    partition_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("favorite_partitions.id", ondelete="CASCADE"),
        nullable=True,
        comment="所在分区。NULL = 默认收藏夹（它不是一行数据，是一个状态）",
    )

    def __repr__(self) -> str:
        """调试时能看到关键信息。"""
        return (
            f"<RecipeFavorite id={self.id} user={self.user_id} "
            f"recipe={self.recipe_id} partition={self.partition_id}>"
        )
