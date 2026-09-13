"""菜谱分类相关的请求与响应模型。

和菜谱模块保持一致：这里只校验"形状"（长度、类型），
具体规则（重名、分类下还有没有菜）放在 Service 层，
因为 Service 抛的业务异常能返回干净的中文提示（400 + 一句人话），
而 Pydantic 的报错会带一堆内部措辞（422 + "Value error, ..."），对用户不友好。
"""

from pydantic import BaseModel, Field

from app.models.recipe_category import DEFAULT_CATEGORY_NAME, MAX_CATEGORY_NAME_LENGTH, RecipeCategory


class CategoryCreateRequest(BaseModel):
    """新增分类请求。"""

    name: str = Field(
        ...,
        min_length=1,
        max_length=MAX_CATEGORY_NAME_LENGTH,
        description="分类名，例如「早餐」。同一家庭组内不能重名",
    )


class CategoryUpdateRequest(BaseModel):
    """修改分类请求。

    第一版只支持改名。排序先不做（新分类一律排在最后），
    因为拖拽排序属于交互细节，等功能稳定了再单独加，避免现在把接口撑大。
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=MAX_CATEGORY_NAME_LENGTH,
        description="新的分类名",
    )


class CategoryInfo(BaseModel):
    """分类信息（返回给前端）。

    带上 recipe_count 而不是让前端自己数，是因为前端拿到的菜谱列表
    可能已经被搜索词或分类筛选过了，数出来的数量会跟着变，
    而侧边栏上的"共几道菜"应该是全量口径，两处口径不一致会很奇怪。
    """

    id: int = Field(..., description="分类 ID")
    space_id: int = Field(..., description="所属家庭组 ID")
    name: str = Field(..., description="分类名")
    sort_order: int = Field(..., description="显示顺序，数字越小越靠前")
    recipe_count: int = Field(default=0, description="该分类下的菜谱数量（全量口径）")
    is_default: bool = Field(
        default=False,
        description=(
            "是否为「新增菜品时默认选中」的分类。"
            "前端据此决定编辑器里默认选哪个，不要自己硬编码分类名——"
            "两边各写一份，改了一边忘了另一边就会对不上。"
        ),
    )

    @classmethod
    def from_model(cls, category: RecipeCategory, recipe_count: int = 0) -> "CategoryInfo":
        """从数据库对象构造。

        is_default 的判定统一放在这里，而不是让每个接口各写一遍。
        "新增菜品时默认选中哪个分类"是一条业务约定，只有一处实现，
        才不会出现"分类列表说是热菜、菜谱详情说是别的"这种自相矛盾。
        """
        return cls(
            id=category.id,
            space_id=category.space_id,
            name=category.name,
            sort_order=category.sort_order,
            recipe_count=recipe_count,
            is_default=category.name == DEFAULT_CATEGORY_NAME,
        )
