"""家庭冰箱（食材库存）相关表。

这是家庭共享域的第二块拼图：菜单负责"家里会做什么菜"，冰箱负责"家里现在有什么食材"。
两者都挂在 space_id 下，全家人都能看到、都能用。

权限口径（用户拍板，和菜单一致）：
    只有家庭组的**创建人**能增删改冰箱里的食材；普通成员只能浏览。
    理由和菜单一样——库存是这个家共享的资料，谁都能改就意味着任何人都能清空、
    删掉别人记的库存，一次误操作代价不可逆；收成一个人管，责任清楚。

关于 created_by：
    只用于展示"谁加的"，不参与权限判断（权限只看 owner_id）。

关于分类/存放：
    分类（蔬菜/肉蛋/水产/调料/饮品/其他）和存放（冷藏/冷冻/常温）都是**自由字符串**，
    由前端给预设选项、后端只存字符串。这样做是为了不把"有哪些分类"写死在数据库里，
    以后想加"母婴""宠物"之类，前端改一下预设即可，不用动表结构。
"""

from datetime import date

from sqlalchemy import BigInteger, Date, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FridgeItem(Base, TimestampMixin):
    """家庭冰箱里的一件食材。一行 = 一种食材（同一种按数量记，不按份拆行）。"""

    __tablename__ = "fridge_items"
    __table_args__ = (
        # 列表接口永远带 space_id 查询，建单列索引最划算。
        # 没有像菜谱那样建 (space_id, category_id) 复合索引，是因为冰箱的筛选维度多
        # （分类、存放、临期），且数据量小（一个家庭几十到几百条），单列 space_id 足够。
        Index("ix_fridge_items_space_id", "space_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="食材 ID",
    )
    space_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("spaces.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属家庭组。家庭组解散时，冰箱里的食材随之清理",
    )
    name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="食材名，例如「鸡蛋」",
    )
    quantity: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="数量。和 unit 配合表达，例如 quantity=10、unit='个'",
    )
    unit: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True,
        comment="单位，例如「个」「克」「盒」「袋」「瓶」「包」",
    )
    category: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment="分类：蔬菜/肉蛋/水产/调料/饮品/其他。前端给预设，后端只存字符串",
    )
    storage: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True,
        comment="存放位置：冷藏/冷冻/常温",
    )
    expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="保质期（日期）。空表示不关注保质期",
    )
    note: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="备注，例如「开封后尽快吃完」",
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        # RESTRICT 而不是 CASCADE：删用户账号绝不能把他家冰箱里的库存一起删掉。
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="添加者用户 ID，仅用于展示「谁加的」",
    )

    def __repr__(self) -> str:
        return f"<FridgeItem id={self.id} space={self.space_id} name={self.name!r}>"
