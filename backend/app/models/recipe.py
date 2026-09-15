"""家庭菜谱（菜单模块）相关表。

这个项目本质是"个人生活工作台"，菜单只是它的第一个模块。
菜谱挂在 space_id 上，属于**家庭共享域**：一个家的菜谱，全家人都能看到、都能用。
以后"我今天吃了什么、摄入了多少热量"会挂在 user_id 上，属于**个人私有域**，
两者刻意分开，互不干扰。

关于创建人（created_by）：
    已经取消"管理员"这套角色设计，只区分"创建家庭组的人"和"普通成员"。
    这里记下 created_by 只是留痕（界面上可以显示"这道菜是妈加的"），
    不参与权限判断——本版本里任何家庭成员都能增删改菜谱。
    将来若真要收紧成"只能改自己加的"，加一个判断即可，不用改表结构。

关于分类（category_id）：
    第一版把分类写死在代码里（字符串），后来升级成独立的一张表，
    见 recipe_category.py 里对这次改动的完整说明。
    这里只保留一条外键，删除规则用 RESTRICT：
    数据库层面就不允许删掉"还有菜挂着的分类"。
    应用层会先查一次数量、给出友好提示（"这个分类下还有 3 道菜"），
    RESTRICT 是最后一道兜底——万一将来有别的写入路径忘了检查，数据库也会拦住。

为什么第一版不做结构化食材（"番茄 200 克"那种）？
    结构化食材会立刻牵出两个下游问题：冰箱里还有没有（库存）、该买什么（采购清单）。
    那属于另外的模块。第一版把做法存成一整段文字就能把"家里会做什么菜"解决掉，
    等模块边界清楚了再拆细，避免现在把范围撑爆。
"""

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# ---------- 辣度 ----------
# 取值范围固定这四档，**顺序就是点单时按钮的排列顺序**。
# 这份定义继承自旧小程序版（那边在云函数和两个页面里各写了一遍，值完全一致），
# 前后端必须一致：后端把 spice_options 随菜谱一起返回，前端只渲染后端给的，不自己拼。
SPICE_LEVELS = ("不辣", "微辣", "正常辣", "特辣")


class Recipe(Base, TimestampMixin):
    """家庭菜谱：一道菜对应一行，归属于某个家庭组。"""

    __tablename__ = "recipes"
    __table_args__ = (
        # 复合索引 (space_id, category_id)。
        # 列表接口永远会带 space_id，而且经常再按分类过滤（点侧边栏某个分类），
        # 所以建复合索引最合适。space_id 又是最左列，
        # 于是"只按 space_id 查"也能走这个索引，不需要再单独建一个。
        #
        # 索引名从 ix_recipes_space_category 改成了 ..._category_id：
        # 名字跟着列走，好处是迁移工具能自动识别出"旧索引没了、新索引要建"。
        # 如果沿用旧名字，工具会以为索引还在，结果新索引根本没建，
        # 而这个索引恰恰是列表接口的性能依赖，属于那种不报错但会慢慢变慢的问题。
        Index("ix_recipes_space_category_id", "space_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="菜谱 ID",
    )
    space_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("spaces.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属家庭组。家庭组解散时，这个家的菜谱随之清理",
    )
    name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="菜名，例如「番茄炒蛋」",
    )
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        # RESTRICT：数据库层面不允许删掉"还有菜挂着"的分类（应用层会先给出友好提示）。
        # 这里绝不能用 CASCADE——那意味着"删掉甜点分类，所有甜点菜谱一起消失"，
        # 用户点一下删除就丢了数据，且撤不回来。
        ForeignKey("recipe_categories.id", ondelete="RESTRICT"),
        nullable=False,
        comment="所属分类 ID。必须属于同一个家庭组（由 Service 层校验，防止挂到别人家的分类上）",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="做法或说明。第一版就存一整段文字，不做结构化食材",
    )
    image_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="菜品图片地址（存上传接口给的相对路径）。为空时前端用分类色底 + 菜名首字占位",
    )
    spice_options: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'::json"),
        comment=(
            "这道菜支持哪几档辣度，取值只能是 SPICE_LEVELS 里的，顺序按 SPICE_LEVELS 归一化。"
            "空数组表示点这道菜时不问辣度（比如汤、饮品）"
        ),
    )
    default_spice: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment="默认辣度，必须是 spice_options 里的一个。为空时取第一档",
    )
    is_sold_out: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment=(
            "「今天不做」：临时标记，比如买了菜回来发现少了食材。"
            "和商家的「库存」不是一回事——这里只是今天先不做这道，随时可以取消"
        ),
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        # 注意这里刻意用 RESTRICT 而不是 CASCADE：
        # 如果某天要删除一个用户账号，绝不能因为他退出就把全家人的菜谱一起删掉。
        # 宁可让删除操作被数据库拦下来，再人工决定这些菜谱怎么处理。
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="添加者用户 ID，仅用于展示「谁加的」，不参与权限判断",
    )

    def __repr__(self) -> str:
        """调试时打印对象能看到关键信息，而不是一串内存地址。"""
        return f"<Recipe id={self.id} space={self.space_id} name={self.name!r} category_id={self.category_id}>"
