"""数据库模型包。

注意：这里必须显式导入全部模型类。
Alembic 自动生成迁移时是通过 Base.metadata 发现表的，
如果某个模型没有被导入过，它就不在 metadata 里，迁移会漏表。
"""

from app.models.base import Base
from app.models.recipe import Recipe
from app.models.recipe_category import (
    DEFAULT_CATEGORY_NAME,
    DEFAULT_CATEGORY_NAMES,
    MAX_CATEGORY_NAME_LENGTH,
    RecipeCategory,
)
from app.models.space import ROLE_ADMIN, ROLE_MEMBER, Space, SpaceMember
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Space",
    "SpaceMember",
    "ROLE_ADMIN",
    "ROLE_MEMBER",
    "Recipe",
    "RecipeCategory",
    "DEFAULT_CATEGORY_NAMES",
    "DEFAULT_CATEGORY_NAME",
    "MAX_CATEGORY_NAME_LENGTH",
]
