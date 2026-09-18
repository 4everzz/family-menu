"""个人健康档案相关的数据模型。

响应模型用 float 输出数值（保证 JSON 里是数字，前端直接当 number 用）；
输入模型接受前端传来的数字（JSON 没有 Decimal，Pydantic 自动转）。

枚举值在服务层做白名单校验，这里只给最大长度这种简单约束。
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.user_profile import MAX_DIET_PREFERENCES_LENGTH


class HealthProfileResponse(BaseModel):
    """返回给前端的健康档案。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    gender: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    goal: Optional[str] = None
    diet_preferences: Optional[str] = None
    updated_at: datetime


class HealthProfileUpdate(BaseModel):
    """修改健康档案（部分更新）。所有字段可选，没传就保持原值。"""

    gender: Optional[str] = Field(default=None, description="性别：male / female / other")
    height_cm: Optional[float] = Field(default=None, description="身高（厘米）")
    weight_kg: Optional[float] = Field(default=None, description="体重（千克）")
    goal: Optional[str] = Field(default=None, description="目标：lose / maintain / gain")
    diet_preferences: Optional[str] = Field(
        default=None,
        max_length=MAX_DIET_PREFERENCES_LENGTH,
        description="饮食备注自由文本，如「减脂期·清淡饮食·忌辛辣」",
    )


class CalorieLogCreate(BaseModel):
    """新增一条热量记录。"""

    eaten_at: Optional[date] = Field(default=None, description="食用日期，默认今天")
    food_name: str = Field(..., max_length=128, description="食物名称")
    calories: float = Field(..., description="估算热量（kcal）")
    portion: Optional[str] = Field(default=None, max_length=64, description="份量描述")
    image_url: Optional[str] = Field(default=None, max_length=512, description="识别用图相对路径")
    source: Optional[str] = Field(default="vision", max_length=16, description="来源 vision / manual")


class CalorieLogUpdate(BaseModel):
    """修改一条热量记录。

    为什么是"整条替换"而不是部分更新（所有字段都必填）？
      调用方是 AI 页的编辑弹层，它手上永远有完整的四个字段。
      做成部分更新的话，"portion 传 null"到底是"清掉份量"还是"没传这个字段"
      就分不清了（Pydantic 里两者都是 None），得额外引入哨兵值——不值得。
      所以这里要求前端总是把整条送回来，语义也就不含糊了。

    注意 `portion` 允许为 null：用户把份量清空 = 这条记录不显示份量。
    """

    eaten_at: date = Field(..., description="食用日期")
    food_name: str = Field(..., min_length=1, max_length=128, description="食物名称")
    calories: float = Field(..., gt=0, description="热量（kcal）")
    portion: Optional[str] = Field(default=None, max_length=64, description="份量描述，可空")


class CalorieLogResponse(BaseModel):
    """返回给前端的一条热量记录。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    eaten_at: date
    food_name: str
    calories: float
    portion: Optional[str] = None
    image_url: Optional[str] = None
    source: str
    created_at: datetime


class FoodEstimate(BaseModel):
    """单条识别结果：一道菜的热量估算。

    ⚠️ 热量不是模型直接报的整份值，而是 `kcal_per_100g × grams / 100` 算出来的。
    这么拆有两个好处：数字可解释（前端能显示「450g × 180 kcal/100g」），
    以及用户可以按份量（小份/中份/大份）缩放——照片里估份量本来就模糊，
    与其让模型猜，不如让最清楚自己吃了多少的人来定。
    """

    food_name: str
    calories: float
    portion: Optional[str] = None
    confidence: Optional[float] = None
    # 这一份的估计克重（模型看图估的），前端拿它当「中份」基准
    grams: Optional[float] = None
    # 每 100 克多少千卡（另用纯文字问得，稳定）。查不到时为 null。
    kcal_per_100g: Optional[float] = None


class RecognizeFoodResponse(BaseModel):
    """拍照识别的返回：可能是多道菜 + 是否占位数据。"""

    items: list[FoodEstimate]
    mock: bool = False
