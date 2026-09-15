"""家庭菜谱相关的请求与响应模型。

这里只校验"形状"（长度、类型这类），具体规则（菜名不能是空白、分类必须属于本家）
放在 Service 层。原因和家庭组模块保持一致：
    Service 抛的业务异常能返回干净的中文提示（400 + 一句人话），
    而 Pydantic 的报错会带一堆内部措辞（422 + "Value error, ..."），对用户不友好。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RecipeCreateRequest(BaseModel):
    """新增菜谱请求。"""

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="菜名，例如「番茄炒蛋」",
    )
    category_id: int = Field(
        ...,
        description="分类 ID，必须属于同一个家庭组。分类清单从分类列表接口取",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="做法或说明，可空",
    )
    image_url: str | None = Field(
        default=None,
        max_length=512,
        description="图片地址（上传接口返回的相对路径），可空。为空时前端用分类色底 + 菜名首字占位",
    )
    spice_options: list[str] = Field(
        default_factory=list,
        max_length=4,
        description=(
            "这道菜支持哪几档辣度，取值见 app/models/recipe.py 的 SPICE_LEVELS。"
            "空数组表示点这道菜时不问辣度（汤、饮品这类）"
        ),
    )
    default_spice: str | None = Field(
        default=None,
        max_length=16,
        description="默认辣度，必须是 spice_options 里的一个；不传则用第一档",
    )
    is_sold_out: bool = Field(
        default=False,
        description="「今天不做」。置为 true 后仍能看到这道菜，但不能加进点单",
    )


class RecipeUpdateRequest(BaseModel):
    """修改菜谱请求（部分更新）。

    每个字段都是可选的，只改传过来的那几个。
    怎么区分"没传这个字段"和"把它显式清空"？
    用 model_dump(exclude_unset=True)：没出现在请求体里的键不会被带出来，
    而显式传了 description: null 的会被带出来（值为 None），于是可以被清空。

    注意 category_id 声明成 int | None 只是为了"可以不传"，
    语义上它不能是 null——真传了 null 会在 Service 层被拒绝，
    因为一道菜必须挂在某个分类下（数据库那列也是 NOT NULL）。
    """

    name: str | None = Field(default=None, min_length=1, max_length=64, description="菜名")
    category_id: int | None = Field(default=None, description="分类 ID，必须属于同一个家庭组")
    description: str | None = Field(default=None, max_length=2000, description="做法或说明")
    image_url: str | None = Field(default=None, max_length=512, description="图片地址")
    spice_options: list[str] | None = Field(
        default=None,
        max_length=4,
        description="支持哪几档辣度。传空数组表示改成「不问辣度」",
    )
    default_spice: str | None = Field(
        default=None,
        max_length=16,
        description=(
            "默认辣度。既可用来换成另一档，也可以传 null 表示「不指定、取第一档」——"
            "所以这里用 exclude_unset 区分「没传」和「传了 null」"
        ),
    )
    is_sold_out: bool | None = Field(default=None, description="「今天不做」")


class RecipeInfo(BaseModel):
    """菜谱信息（返回给前端）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="菜谱 ID")
    space_id: int = Field(..., description="所属家庭组 ID")
    name: str = Field(..., description="菜名")
    category_id: int = Field(..., description="所属分类 ID")
    category_name: str = Field(
        ...,
        description=(
            "分类名。这里直接给名字、而不是让前端自己去分类列表里查，"
            "是因为卡片上要按分类显示对应的图标和底色，前端每次渲染都得查一遍映射表；"
            "后端多 join 一次就能给全，前端少一份容易走偏的映射逻辑。"
        ),
    )
    description: str | None = Field(default=None, description="做法或说明")
    image_url: str | None = Field(default=None, description="图片地址")
    spice_options: list[str] = Field(
        default_factory=list,
        description="这道菜支持哪几档辣度。空数组表示点它时不问辣度（前端据此决定要不要弹选择框）",
    )
    default_spice: str | None = Field(
        default=None,
        description="默认辣度。为空时前端取 spice_options 的第一档",
    )
    is_sold_out: bool = Field(
        default=False,
        description="「今天不做」。前端据此显示「已售罄」并禁用加菜按钮",
    )
    created_by: int = Field(..., description="添加者用户 ID")
    created_by_nickname: str | None = Field(
        default=None,
        description="添加者昵称，前端用来显示「谁加的」，省一次查成员列表的请求",
    )
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后修改时间")
