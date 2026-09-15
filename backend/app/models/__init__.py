"""数据库模型包。

注意：这里必须显式导入全部模型类。
Alembic 自动生成迁移时是通过 Base.metadata 发现表的，
如果某个模型没有被导入过，它就不在 metadata 里，迁移会漏表。
"""

from app.models.base import Base
from app.models.dish_order import (
    ORDER_STATUS_DONE,
    ORDER_STATUS_PENDING,
    DishOrder,
    DishOrderItem,
)
from app.models.favorite import FavoritePartition, RecipeFavorite
from app.models.fridge_item import FridgeItem
from app.models.recipe import Recipe
from app.models.recipe_category import (
    DEFAULT_CATEGORY_NAME,
    DEFAULT_CATEGORY_NAMES,
    MAX_CATEGORY_NAME_LENGTH,
    RecipeCategory,
)
from app.models.space import ROLE_ADMIN, ROLE_MEMBER, Space, SpaceMember
from app.models.user import DEFAULT_NICKNAME, USERNAME_MAX_LENGTH, USERNAME_MIN_LENGTH, User
from app.models.user_identity import PROVIDER_WX_MP, UserIdentity
from app.models.user_profile import CalorieLog, UserProfile

__all__ = [
    "Base",
    "User",
    "UserIdentity",
    "PROVIDER_WX_MP",
    "DEFAULT_NICKNAME",
    "USERNAME_MIN_LENGTH",
    "USERNAME_MAX_LENGTH",
    "Space",
    "SpaceMember",
    "ROLE_ADMIN",
    "ROLE_MEMBER",
    "Recipe",
    "RecipeCategory",
    "FridgeItem",
    "DishOrder",
    "DishOrderItem",
    "ORDER_STATUS_PENDING",
    "ORDER_STATUS_DONE",
    "FavoritePartition",
    "RecipeFavorite",
    "DEFAULT_CATEGORY_NAMES",
    "DEFAULT_CATEGORY_NAME",
    "MAX_CATEGORY_NAME_LENGTH",
    "UserProfile",
    "CalorieLog",
]
