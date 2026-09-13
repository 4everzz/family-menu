"""菜谱分类表。

为什么从"写死的分类"改成"一张表"？
    第一版把 6 个分类（凉菜/热菜/汤羹/主食/甜点/饮品）写死在代码里。
    好处是侧边栏永远整齐，坏处是用户没法加自己习惯的分类（"早餐""夜宵""宝宝餐"）。
    现在改成一张表：每个家庭组有一套自己的分类，可以新增、改名、删除。

    写死常量 → 数据表，看起来只是搬了个家，实际上是**数据模型的升级**：
    分类从"程序的一部分"变成了"用户的数据"。后者才能被用户自己管。

为什么菜谱存 category_id 外键，而不是继续在菜谱表里存分类名？
    1. 改名零成本：改这一行，所有菜都跟着变；要是存名字，改名得批量更新所有菜谱。
    2. 重名由数据库挡：有唯一约束在，不可能出现两个"汤羹"；靠代码自觉迟早漏。
    3. 删除有兜底：菜谱那边的外键设成 RESTRICT，数据库层面就不允许删掉还有菜的分类。

一个家庭组一套分类，而不是全局共用一套：
    分类是"这家人怎么组织自己的菜"，本来就该各管各的。
    而且这样做，某家人删掉自己的"甜点"分类，完全不会影响别人家。
"""

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# 新建家庭组时自动带上的默认分类。
#
# 顺序就是前端侧边栏的显示顺序，所以这里的先后是有意义的（sort_order 按这个顺序赋 0..N-1）。
# 之所以还要给默认值，是因为"完全空白"的侧边栏会让新用户不知道能干什么；
# 先给一套合理的，不合适他自己改。
DEFAULT_CATEGORY_NAMES: tuple[str, ...] = ("凉菜", "热菜", "汤羹", "主食", "甜点", "饮品")

# 新增菜品时前端默认选中的分类。
#
# 为什么不直接用"第一个分类"？因为第一个是"凉菜"，而家常菜里最常见的显然不是凉菜，
# 每次加菜都要手动改一下分类，很烦。
# 这个常量放在后端，前端从分类列表接口里取"哪个是默认"，不要自己硬编码字符串——
# 两边各写一份，改了一边忘了另一边就会对不上。
DEFAULT_CATEGORY_NAME = "热菜"

# 分类名长度上限。和数据库列宽保持一致，改的时候两边一起改。
MAX_CATEGORY_NAME_LENGTH = 16


class RecipeCategory(Base, TimestampMixin):
    """家庭组的菜谱分类。每个家庭组一套。"""

    __tablename__ = "recipe_categories"
    __table_args__ = (
        # 同一个家庭组内不允许重名分类。
        # 这条约束交给数据库而不是应用层，是因为将来可能有多个写入路径
        # （手动新增、批量导入、数据修复脚本），任何一条路径忘了查重都会留下脏数据，
        # 而数据库约束只有一处、绕不过去。
        UniqueConstraint("space_id", "name", name="uq_recipe_categories_space_name"),
        # 列表查询永远是"某个家庭组的分类，按顺序排"，这个复合索引正好覆盖。
        # space_id 是最左列，所以"只要 space_id 不要排序"的查询也能走它。
        Index("ix_recipe_categories_space_sort", "space_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="分类 ID",
    )
    space_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("spaces.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属家庭组。家庭组解散时，这个家的分类随之清理",
    )
    name: Mapped[str] = mapped_column(
        String(MAX_CATEGORY_NAME_LENGTH),
        nullable=False,
        comment="分类名，例如「热菜」。同一家庭组内不允许重复",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="显示顺序，数字越小越靠前。新增的分类排在最后",
    )

    def __repr__(self) -> str:
        """调试时打印对象能看到关键信息，而不是一串内存地址。"""
        return f"<RecipeCategory id={self.id} space={self.space_id} name={self.name!r} sort={self.sort_order}>"
