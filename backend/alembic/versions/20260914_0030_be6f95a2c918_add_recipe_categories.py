"""add recipe categories

Revision ID: be6f95a2c918
Revises: 25bfc5bdf007
Create Date: 2026-09-14 00:30:27.300594+08:00

把"菜谱分类"从写死在代码里的常量，升级成一张真正的数据表。

这是一次**带存量数据搬运的结构变更**，比单纯加表要小心，涉及三件事：
    1. 新建分类表；
    2. 给每个已经存在的家庭组补上 6 个默认分类，否则它们会变成"没有任何分类的家"；
    3. 把每条老菜谱的 `category` 字符串（"热菜"）翻译成新分类的 id。

autogenerate 只做了第 1 件，剩下的必须手写——它只会比对结构，
判断不了"这些数据应该怎么搬家"。下面每一段都标注了"为什么必须这么做"。

关于脚本里硬编码的分类名（凉菜/热菜/…）：
    迁移脚本刻意**不 import 应用代码里的常量**。
    因为迁移要能在任何时候原样重放，而应用代码是会继续变的——
    今天从常量里读，明天常量改了，这段"历史"就跟着变了，回放出来的结果和当年不一致。
    迁移脚本记录的是"当时发生了什么"，所以这里就该写死。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# 迁移标识（Alembic 用它串起版本链，不要手改）
revision: str = 'be6f95a2c918'
down_revision: str | None = '25bfc5bdf007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 菜谱表上那条外键的名字，downgrade 时要按名字删，所以必须先起名。
# autogenerate 默认生成无名的外键（op.create_foreign_key(None, ...)），
# 那样回滚时会因为"不知道要删哪个约束"而直接失败。
FK_RECIPES_CATEGORY = "fk_recipes_category_id_recipe_categories"

CATEGORY_ID_COMMENT = "所属分类 ID。必须属于同一个家庭组（由 Service 层校验，防止挂到别人家的分类上）"


def upgrade() -> None:
    """升级：把数据库结构改到本版本的样子。"""
    # ---------- 第一步：建分类表 ----------
    op.create_table(
        'recipe_categories',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='分类 ID'),
        sa.Column(
            'space_id',
            sa.BigInteger(),
            nullable=False,
            comment='所属家庭组。家庭组解散时，这个家的分类随之清理',
        ),
        sa.Column(
            'name',
            sa.String(length=16),
            nullable=False,
            comment='分类名，例如「热菜」。同一家庭组内不允许重复',
        ),
        sa.Column(
            'sort_order',
            sa.Integer(),
            nullable=False,
            comment='显示顺序，数字越小越靠前。新增的分类排在最后',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='创建时间',
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='更新时间',
        ),
        sa.ForeignKeyConstraint(['space_id'], ['spaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('space_id', 'name', name='uq_recipe_categories_space_name'),
    )
    op.create_index(
        'ix_recipe_categories_space_sort',
        'recipe_categories',
        ['space_id', 'sort_order'],
        unique=False,
    )

    # ---------- 第二步：给每个已有家庭组补一套默认分类 ----------
    # 一条 INSERT ... SELECT 就够，不用在 Python 里循环查库、一条条插——
    # 那样每个家庭组都要一次数据库往返，数据一多会非常慢，而且中途失败很难收拾。
    # CROSS JOIN 的意思是"每个家庭组 × 6 个分类"，也就是笛卡尔积，
    # 正好是"给每个家都来一套"。
    op.execute(
        """
        INSERT INTO recipe_categories (space_id, name, sort_order)
        SELECT s.id, c.name, c.sort_order
        FROM spaces s
        CROSS JOIN (
            VALUES
                ('凉菜', 0), ('热菜', 1), ('汤羹', 2),
                ('主食', 3), ('甜点', 4), ('饮品', 5)
        ) AS c(name, sort_order)
        """
    )

    # ---------- 第三步：加新列 ----------
    # 关键：这里必须写成 nullable=True（可空）。
    # 如果直接按模型定义加成 NOT NULL，PostgreSQL 会因为"表里已有数据、
    # 但这些数据的这一列没有值"而拒绝执行——这是很常见的迁移事故。
    # 正确做法是"先可空地加上 → 填数据 → 再收紧成 NOT NULL"，分三步走。
    op.add_column(
        'recipes',
        sa.Column('category_id', sa.BigInteger(), nullable=True, comment=CATEGORY_ID_COMMENT),
    )

    # ---------- 第四步：把老菜谱的分类名翻译成新分类 id ----------
    # 老的 recipes.category 存的是名字（"热菜"），现在要换成对应的分类 id。
    # 按 (space_id, name) 关联，保证翻译到的是**这个家自己的**那个分类。
    op.execute(
        """
        UPDATE recipes r
        SET category_id = c.id
        FROM recipe_categories c
        WHERE c.space_id = r.space_id
          AND c.name = r.category
        """
    )

    # ---------- 第五步：兜底 ----------
    # 理论上第四步应该全部命中（老数据里的分类名受代码约束，只可能是那 6 个）。
    # 但"理论上应该"不等于"实际一定"，所以留一手：
    # 万一有历史脏数据或手工改过的记录没匹配上，就把它归到本家的第一个分类，
    # 而不是留下 NULL —— 留着 NULL 会在下一步被数据库拒绝，报一个很难懂的错误。
    op.execute(
        """
        UPDATE recipes r
        SET category_id = (
            SELECT c.id
            FROM recipe_categories c
            WHERE c.space_id = r.space_id
            ORDER BY c.sort_order, c.id
            LIMIT 1
        )
        WHERE r.category_id IS NULL
        """
    )

    # 明确检查一次：宁可在这里抛一句看得懂的话，也不要等下面 alter_column 报
    # "column contains null values" 那种让人一头雾水的错误。
    conn = op.get_bind()
    orphan_count = conn.execute(
        sa.text("SELECT count(*) FROM recipes WHERE category_id IS NULL")
    ).scalar_one()
    if orphan_count:
        raise RuntimeError(
            f"还有 {orphan_count} 条菜谱没能归入任何分类，迁移中止——"
            "请先确认这些菜谱的 space_id 是否有对应的家庭组"
        )

    # ---------- 第六步：收紧成 NOT NULL ----------
    op.alter_column(
        'recipes',
        'category_id',
        existing_type=sa.BigInteger(),
        nullable=False,
        comment=CATEGORY_ID_COMMENT,
    )

    # ---------- 第七步：索引与外键 ----------
    # 旧索引建在即将被删掉的 category 列上，先删掉它，再建新的。
    # 注意顺序：删索引要放在删列之前。虽然 PostgreSQL 在删列时会自动带走依赖它的索引，
    # 但那样走的是"隐式删除"，迁移记录里看不出发生了什么。
    op.drop_index(op.f('ix_recipes_space_category'), table_name='recipes')
    op.create_index(
        'ix_recipes_space_category_id',
        'recipes',
        ['space_id', 'category_id'],
        unique=False,
    )
    op.create_foreign_key(
        FK_RECIPES_CATEGORY,
        'recipes',
        'recipe_categories',
        ['category_id'],
        ['id'],
        ondelete='RESTRICT',
    )

    # ---------- 第八步：删掉旧列 ----------
    op.drop_column('recipes', 'category')


def downgrade() -> None:
    """回滚：把本版本的改动撤销掉。

    ⚠️ 这次回滚是**有损**的，必须清楚：
        分类名会被写回菜谱表的字符串列，而"分类"这个概念本身消失了。
        用户自己新建的分类（比如"早餐"）在回滚后就没了，
        再执行一次 upgrade 时也找不回来——那时的分类名不在默认 6 类里，
        会被兜底逻辑归到第一个分类。
        这是结构变更本身带来的代价，不是脚本写得不好。
        所以能不用回滚就别用；真要回，先备份。
    """
    # ---------- 第一步：加回旧列（可空） ----------
    op.add_column(
        'recipes',
        sa.Column(
            'category',
            sa.VARCHAR(length=16),
            autoincrement=False,
            nullable=True,
            comment='分类，取值必须是 RECIPE_CATEGORIES 之一',
        ),
    )

    # ---------- 第二步：把分类名写回字符串列 ----------
    op.execute(
        """
        UPDATE recipes r
        SET category = c.name
        FROM recipe_categories c
        WHERE c.id = r.category_id
        """
    )

    # ---------- 第三步：收紧成 NOT NULL ----------
    # 兜底：理论上第二步已经把所有菜谱都填上了，这里再兜一次防意外
    op.execute("UPDATE recipes SET category = '热菜' WHERE category IS NULL")
    op.alter_column(
        'recipes',
        'category',
        existing_type=sa.VARCHAR(length=16),
        nullable=False,
        comment='分类，取值必须是 RECIPE_CATEGORIES 之一',
    )

    # ---------- 第四步：拆掉索引与外键 ----------
    # 外键必须按名字删——这就是上面给它起名的原因
    op.drop_constraint(FK_RECIPES_CATEGORY, 'recipes', type_='foreignkey')
    op.drop_index('ix_recipes_space_category_id', table_name='recipes')
    op.create_index(
        op.f('ix_recipes_space_category'),
        'recipes',
        ['space_id', 'category'],
        unique=False,
    )

    # ---------- 第五步：删列、删表 ----------
    op.drop_column('recipes', 'category_id')
    op.drop_index('ix_recipe_categories_space_sort', table_name='recipe_categories')
    op.drop_table('recipe_categories')
