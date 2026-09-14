"""家庭冰箱相关的请求与响应模型。

只校验"形状"（长度、类型），具体规则（食材名不能为空、数量必须为正）
放在 Service 层，原因和菜谱一致：Service 抛的业务异常能返回干净的中文提示，
而 Pydantic 的 422 报错对用户不友好。
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class FridgeItemCreateRequest(BaseModel):
    """新增食材请求。"""

    name: str = Field(..., min_length=1, max_length=64, description="食材名，例如「鸡蛋」")
    quantity: float = Field(..., gt=0, le=99999.99, description="数量，必须大于 0")
    unit: str | None = Field(default=None, max_length=8, description="单位，例如「个」「克」「盒」")
    category: str | None = Field(
        default=None, max_length=16, description="分类：蔬菜/肉蛋/水产/调料/饮品/其他"
    )
    storage: str | None = Field(default=None, max_length=8, description="存放：冷藏/冷冻/常温")
    expiry_date: date | None = Field(default=None, description="保质期（日期），可空")
    note: str | None = Field(default=None, max_length=200, description="备注，可空")


class FridgeItemUpdateRequest(BaseModel):
    """修改食材请求（部分更新）。

    每个字段都可选，只改传过来的那几个。
    用 model_dump(exclude_unset=True) 区分"没传"和"显式清空（传 null）"。
    quantity 声明成 float | None 只是为了"可以不传"，语义上不能是 0 或负数。
    """

    name: str | None = Field(default=None, min_length=1, max_length=64, description="食材名")
    quantity: float | None = Field(default=None, gt=0, le=99999.99, description="数量")
    unit: str | None = Field(default=None, max_length=8, description="单位")
    category: str | None = Field(default=None, max_length=16, description="分类")
    storage: str | None = Field(default=None, max_length=8, description="存放")
    expiry_date: date | None = Field(default=None, description="保质期（日期）")
    note: str | None = Field(default=None, max_length=200, description="备注")


class FridgeItemInfo(BaseModel):
    """食材信息（返回给前端）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="食材 ID")
    space_id: int = Field(..., description="所属家庭组 ID")
    name: str = Field(..., description="食材名")
    quantity: float = Field(..., description="数量")
    unit: str | None = Field(default=None, description="单位")
    category: str | None = Field(default=None, description="分类")
    storage: str | None = Field(default=None, description="存放")
    expiry_date: date | None = Field(default=None, description="保质期（日期）")
    note: str | None = Field(default=None, description="备注")
    is_expiring: bool = Field(
        ...,
        description=(
            "是否临近过期或已过期（服务端按今天 + 7 天窗口算出）。"
            "前端据此高亮，具体「还有几天 / 已过期」由前端用 expiry_date 自己算更准"
        ),
    )
    created_by: int = Field(..., description="添加者用户 ID")
    created_by_nickname: str | None = Field(default=None, description="添加者昵称")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后修改时间")
