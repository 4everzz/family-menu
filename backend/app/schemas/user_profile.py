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
    """单条识别结果：一道菜的热量估算。"""

    food_name: str
    calories: float
    portion: Optional[str] = None
    confidence: Optional[float] = None


class RecognizeFoodResponse(BaseModel):
    """拍照识别的返回：可能是多道菜 + 是否占位数据。"""

    items: list[FoodEstimate]
    mock: bool = False
