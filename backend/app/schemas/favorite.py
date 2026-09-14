"""个人收藏相关的请求与响应模型。

校验分工和其它模块一致：这里只管"形状"（长度、类型），
业务规则（分区名不能重名、数量上限、分区必须属于自己）在 Service 层。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PartitionCreateRequest(BaseModel):
    """新建收藏分区请求。"""

    name: str = Field(
        ...,
        min_length=1,
        max_length=16,
        description="分区名，例如「想吃」「孩子爱吃」，同一用户内不可重名",
    )


class PartitionInfo(BaseModel):
    """一个收藏分区（含收藏数量）。

    默认收藏夹也会出现在这个列表里——它的 id 是 None，
    前端据此把它排在第一位、并且不给删除按钮。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(
        ...,
        description="分区 ID。None 表示默认收藏夹（它不是一行数据，是一个状态）",
    )
    name: str = Field(..., description="分区名。默认收藏夹固定叫「默认收藏夹」")
    count: int = Field(default=0, description="这个分区下有几道收藏的菜")
    isDefault: bool = Field(..., description="是否是默认收藏夹")


class FavoriteToggleRequest(BaseModel):
    """收藏 / 移动分区请求。

    partition_id 传 None（或不传）= 收进默认收藏夹；
    传了就必须是**这个用户自己**的分区——由 Service 校验，
    否则拿着别人的分区 ID 就能把收藏塞进别人家的清单里。
    """

    partition_id: int | None = Field(
        default=None,
        description="目标分区 ID。不传或传 null = 默认收藏夹",
    )


class FavoriteRecipeItem(BaseModel):
    """收藏列表里的一条：菜谱摘要 + 收藏时间。"""

    model_config = ConfigDict(from_attributes=True)

    recipeId: int = Field(..., description="菜谱 ID")
    name: str = Field(..., description="菜名")
    description: str | None = Field(default=None, description="简介，可为空")
    image_url: str | None = Field(default=None, description="菜品图片地址，可为空")
    spaceId: int = Field(..., description="这道菜属于哪个家庭组（点进去要用）")
    spaceName: str = Field(..., description="家庭组名，收藏可能来自不同的家")
    categoryName: str | None = Field(default=None, description="分类名，可空（菜谱被删时拿不到）")
    partitionId: int | None = Field(..., description="所在分区。None = 默认收藏夹")
    favoritedAt: datetime = Field(..., description="收藏时间，列表按它倒序")


class FavoriteListResponse(BaseModel):
    """收藏列表接口的返回。"""

    model_config = ConfigDict(from_attributes=True)

    favorites: list[FavoriteRecipeItem] = Field(default_factory=list, description="收藏的菜")
    total: int = Field(default=0, description="总数（便于前端显示「共 N 道」）")
