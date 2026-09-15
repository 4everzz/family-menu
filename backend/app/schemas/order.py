"""点单相关的请求与响应模型。

和菜谱/冰箱一样：这里只校验"形状"（类型、条数、长度），
业务规则（菜谱是否属于本家、点单是否存在）放在 Service 层——
Service 抛的业务异常能返回干净的中文提示，而 Pydantic 内置约束报的是英文。

⚠️ 所以下面的条数、份数校验都刻意写成自定义校验器，而不是用 ge / le / min_length：
   那些内置约束的报错是 "Input should be greater than or equal to 1"，
   会原样显示给用户。自定义校验器能保证每一句都是中文。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.dish_order import (
    MAX_GUEST_NAME_LENGTH,
    MAX_ITEM_QUANTITY,
    MAX_ORDER_ITEMS,
    MAX_REMARK_LENGTH,
    ORDER_STATUS_DONE,
    ORDER_STATUS_PENDING,
)

ALLOWED_STATUSES = (ORDER_STATUS_PENDING, ORDER_STATUS_DONE)


def _clean_optional_text(value: str | None, max_len: int, label: str) -> str | None:
    """清洗可选文本：去首尾空格，空串一律转 None。

    空串和 None 在语义上都是"没填"，没必要在库里同时存在两种表示。
    """
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned[:max_len] or None


class OrderItemRequest(BaseModel):
    """点单里的一道菜。"""

    recipe_id: int = Field(..., description="菜谱 ID，必须属于同一个家庭组")
    spice: str | None = Field(
        default=None,
        max_length=16,
        description=(
            "选的辣度，取值见 app/models/recipe.py 的 SPICE_LEVELS。"
            "菜谱没设辣度档位（spice_options 为空）时不用传"
        ),
    )
    quantity: int = Field(default=1, description=f"份数，1 ~ {MAX_ITEM_QUANTITY}")

    @field_validator("quantity")
    @classmethod
    def _check_quantity(cls, value: int) -> int:
        """份数校验。

        用自定义校验器而不是 Field(ge=1, le=20)：
        内置约束报的是英文（"Input should be greater than or equal to 1"），
        而这些消息会原样显示给用户。
        """
        if value < 1:
            raise ValueError("份数至少 1 份")
        if value > MAX_ITEM_QUANTITY:
            raise ValueError(f"单道菜最多 {MAX_ITEM_QUANTITY} 份")
        return value


class OrderCreateRequest(BaseModel):
    """提交点单。"""

    guest_name: str | None = Field(
        default=None,
        max_length=MAX_GUEST_NAME_LENGTH,
        description="这单是谁点的，可不填。客人借手机点时填客人名字，方便认单",
    )
    remark: str | None = Field(
        default=None,
        max_length=MAX_REMARK_LENGTH,
        description="整单备注，例如「少辣、不要香菜」",
    )
    items: list[OrderItemRequest] = Field(..., description="点了哪几道菜，至少一道")

    @field_validator("items")
    @classmethod
    def _check_items(cls, value: list[OrderItemRequest]) -> list[OrderItemRequest]:
        """校验菜的道数。"""
        if not value:
            raise ValueError("请至少点一道菜")
        if len(value) > MAX_ORDER_ITEMS:
            raise ValueError(f"一单最多点 {MAX_ORDER_ITEMS} 道菜")
        return value

    @field_validator("guest_name")
    @classmethod
    def _clean_guest_name(cls, value: str | None) -> str | None:
        return _clean_optional_text(value, MAX_GUEST_NAME_LENGTH, "点单人")

    @field_validator("remark")
    @classmethod
    def _clean_remark(cls, value: str | None) -> str | None:
        return _clean_optional_text(value, MAX_REMARK_LENGTH, "备注")


class OrderStatusUpdateRequest(BaseModel):
    """修改点单状态。

    目前只有一件事可改：把这单标记成"已完成"、或者撤回成"待处理"。
    """

    status: str = Field(..., description=f"目标状态：{ORDER_STATUS_PENDING} 或 {ORDER_STATUS_DONE}")

    @field_validator("status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in ALLOWED_STATUSES:
            raise ValueError(f"状态只能是 {' 或 '.join(ALLOWED_STATUSES)}")
        return cleaned


class OrderItemInfo(BaseModel):
    """返回给前端的一条点单明细。"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="明细 ID")
    recipe_id: int | None = Field(
        default=None,
        description="对应菜谱 ID。菜谱被删后为 null，但 dish_name 仍然可用",
    )
    dish_name: str = Field(..., description="菜名（下单时的快照）")
    spice: str | None = Field(
        default=None,
        description="辣度（下单时的快照）。没选辣度时为 null，前端跳过这一行",
    )
    quantity: int = Field(..., description="份数")


class OrderInfo(BaseModel):
    """返回给前端的一张点单。"""

    id: int = Field(..., description="点单 ID")
    space_id: int = Field(..., description="所属家庭组 ID")
    created_by: int = Field(..., description="提交者用户 ID")
    created_by_nickname: str | None = Field(
        default=None,
        description="提交者昵称，省得前端为了显示「谁提交的」再查一次成员列表",
    )
    guest_name: str | None = Field(default=None, description="这单是谁点的（自由填写）")
    remark: str | None = Field(default=None, description="整单备注")
    status: str = Field(..., description=f"{ORDER_STATUS_PENDING}=待处理，{ORDER_STATUS_DONE}=已完成")
    created_at: datetime = Field(..., description="提交时间")
    can_manage: bool = Field(
        default=False,
        description="当前请求者能不能管这张单（改状态 / 删除）。由后端判定，前端只管显示",
    )
    items: list[OrderItemInfo] = Field(default_factory=list, description="点了哪几道菜")
    dish_count: int = Field(default=0, description="一共几道菜（明细条数，方便前端直接显示）")
    total_quantity: int = Field(default=0, description="一共几份（各道菜份数之和）")
