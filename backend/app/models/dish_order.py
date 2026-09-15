"""点单相关表。

场景（用户 2026-09-15 明确）：
    家里来客人时点单——看菜单 → 选菜 → 提交，**不需要付款，菜品也不设价格**。
    常客加入家庭组自己点；临时客人就拿创建人的手机点。

和菜单/冰箱的关系：
    点单是家庭共享域的第三块。菜单回答"这个家会做什么菜"，
    冰箱回答"家里现在有什么食材"，点单回答"今天要做哪几道、各做几份"。

⚠️ 为什么点单表要存菜名快照（dish_name）？
    点单记录会一直留着（"上次那桌客人点了什么"），而菜谱是会被改甚至被删的。
    如果只存 recipe_id：
      · 用 RESTRICT → 只要有人点过这道菜，菜谱就再也删不掉了；
      · 用 CASCADE → 删掉菜谱会把历史点单里的那一项也悄悄抹掉，记录变得不可信。
    所以做成"recipe_id（可空，SET NULL）+ dish_name 快照"：
    下单时把当时的菜名抄一份存下来，之后菜谱怎么改怎么删都不影响已有记录。

权限口径：
    提交点单——**任何家庭成员都能做**（点单是"提需求"，不是"改菜单"）；
    标记完成 / 删除点单——**仅创建人**（和菜单、冰箱的写权限保持一致，责任清楚）。
    created_by 记录的是"谁提交的"，用于展示，不参与权限判断。
"""

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# ---------- 点单状态 ----------
ORDER_STATUS_PENDING = "pending"  # 待处理（刚提交，还没做）
ORDER_STATUS_DONE = "done"  # 已完成（菜做好了 / 这单结束了）

# ---------- 长度与数量上限 ----------
MAX_GUEST_NAME_LENGTH = 32  # "这单是谁点的"，例如「张三」
MAX_REMARK_LENGTH = 200  # 备注，例如「少辣、不要香菜」
MAX_ITEM_QUANTITY = 20  # 单道菜最多几份
MAX_ORDER_ITEMS = 30  # 一单最多几道菜


class DishOrder(Base, TimestampMixin):
    """一张点单。一行 = 客人（或家人）提交的一次点菜。"""

    __tablename__ = "dish_orders"
    __table_args__ = (
        # 列表接口永远按 (space_id, status) 查，建复合索引正好覆盖
        Index("ix_dish_orders_space_status", "space_id", "status"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="点单 ID",
    )
    space_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("spaces.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属家庭组。家庭组解散时，点单记录随之清理",
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        # RESTRICT 而不是 CASCADE：删账号绝不能把这个人提交过的点单记录一起删掉
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="提交者用户 ID。临时客人用创建人手机点时，这里记的就是创建人",
    )
    guest_name: Mapped[str | None] = mapped_column(
        String(MAX_GUEST_NAME_LENGTH),
        nullable=True,
        comment="这单是谁点的（自由填写）。客人借创建人手机点时填客人名字，家人自己点可以留空",
    )
    remark: Mapped[str | None] = mapped_column(
        String(MAX_REMARK_LENGTH),
        nullable=True,
        comment="整单备注，例如「少辣、不要香菜」",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ORDER_STATUS_PENDING,
        comment="点单状态：pending=待处理，done=已完成",
    )

    def __repr__(self) -> str:
        return f"<DishOrder id={self.id} space={self.space_id} status={self.status!r}>"


class DishOrderItem(Base, TimestampMixin):
    """点单里的一道菜。一行 = 某张点单上的一道菜及其份数。"""

    __tablename__ = "dish_order_items"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键",
    )
    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dish_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属点单。点单删掉时明细一起删",
    )
    recipe_id: Mapped[int | None] = mapped_column(
        BigInteger,
        # SET NULL 而不是 RESTRICT/CASCADE：菜谱删了，这条历史点单还要留着（靠 dish_name 显示）。
        # 详见本文件开头关于"菜名快照"的说明。
        ForeignKey("recipes.id", ondelete="SET NULL"),
        nullable=True,
        comment="对应的菜谱 ID。菜谱被删后置空，展示一律用 dish_name",
    )
    dish_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="下单那一刻的菜名快照。菜谱之后改名或删除都不影响这条记录",
    )
    spice: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment=(
            "下单时选的辣度快照。和 dish_name 是同一个道理——"
            "菜单以后改了辣度档位，这张历史单依然说得清当时要的是什么口味"
        ),
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="份数，至少 1 份",
    )

    def __repr__(self) -> str:
        return f"<DishOrderItem order={self.order_id} dish={self.dish_name!r} x{self.quantity}>"
