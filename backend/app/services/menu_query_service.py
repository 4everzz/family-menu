"""菜单数据的「查询 + 整形」层：给 App 内的 Agent 和对外暴露的 MCP Server 共用。

⭐ 为什么单独抽这一层？
    `app/agent/tools.py`（App 自己的 Agent）和 `app/mcp/server/tools.py`（对外的 MCP Server）
    都要回答同样几个问题：冰箱里有什么、什么快过期、有哪些菜、有哪些分类。
    两边要的形状也一模一样——JSON 友好的纯字典，并且带 `days_left` 这种
    **服务端算好的**派生值。

    如果各写一份，早晚会出现"App 里说还能放 5 天、MCP 那边算成 6 天"这种不一致，
    而且这种 bug 极难发现——两个入口不会同时打开来对照。

    所以：**「查什么、怎么整形」收在这里，「用什么协议暴露出去」留给各自那一层。**

    ⭐ 这也正是两条路的关系：**协议可以有两套，数据口径只能有一套。**

⚠️ 这里的方法**都带权限校验**（底层 service 里的 `ensure_member`）。
   调用方不需要也不应该自己再查一遍，但**绝不能绕过这一层直接查库**——
   绕过去就等于绕掉了权限闸门。
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.models.fridge_item import FridgeItem
from app.models.recipe import Recipe
from app.repositories.category_repo import CategoryRepository
from app.repositories.fridge_repo import FridgeRepository
from app.repositories.recipe_repo import RecipeRepository
from app.repositories.space_repo import SpaceRepository
from app.services.category_service import CategoryService
from app.services.fridge_service import FridgeService
from app.services.recipe_service import RecipeService
from app.services.space_service import SpaceService

#: 临期窗口（天）。与 App「临期提醒」用的是同一个值，改这里两边一起变。
EXPIRING_WITHIN_DAYS = 7

#: 让模型传"往后看几天"时的上限保护。
#: 传 3650 就不叫"临期"了，那叫"全库"，而且会把一大堆无关数据灌进上下文。
MAX_EXPIRING_DAYS = 30


def clamp_expiring_days(days: Any) -> int:
    """把模型给的"往后看几天"收敛到 [1, MAX_EXPIRING_DAYS]。

    模型可能传字符串、负数、天文数字——一律夹到合理区间，
    而不是报错让整轮对话失败（这种小毛病不该毁掉一次交互）。
    """
    try:
        value = int(days)
    except (TypeError, ValueError):
        return EXPIRING_WITHIN_DAYS
    return max(1, min(value, MAX_EXPIRING_DAYS))


def days_left(expiry_date: date | None, today: date) -> int | None:
    """算保质期还剩几天。负数表示已经过期了几天。

    ⭐ 为什么在服务端算，而不是把日期丢给模型让它自己减？
       因为**模型不知道"今天"是哪天**——它的时间概念来自训练数据，不可靠。
       这种确定的算术给结果最省事，也最准。这是它和"按烹饪方式估热量"
       那种真正需要判断的事的分界线。
    """
    if expiry_date is None:
        return None
    return (expiry_date - today).days


def is_expiring(left: int | None) -> bool:
    """是否进入临期窗口（含已过期）。"""
    return left is not None and left <= EXPIRING_WITHIN_DAYS


def _jsonable(value: Any) -> Any:
    """把数据库里取出来的值转成能直接 json.dumps 的类型。

    `date` → ISO 字符串（模型读 `2026-09-20` 比读时间戳自然得多）；
    `Decimal` → float（否则 json.dumps 会直接抛错）。
    """
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def fridge_item_to_dict(item: FridgeItem, today: date) -> dict:
    """冰箱条目 + 算好的 `days_left` / `is_expiring`。

    多出来的两个字段是**给模型用的**：它不需要自己算，也不该自己算。
    """
    left = days_left(item.expiry_date, today)
    return {
        "id": item.id,
        "name": item.name,
        "quantity": _jsonable(item.quantity),
        "unit": item.unit,
        "category": item.category,
        "storage": item.storage,
        "expiry_date": _jsonable(item.expiry_date),
        "note": item.note,
        "days_left": left,
        "is_expiring": is_expiring(left),
    }


def recipe_to_dict(recipe: Recipe, category_name: str | None) -> dict:
    """菜谱条目。`category_name` 不在模型上，是 service 关联查出来的。"""
    return {
        "id": recipe.id,
        "name": recipe.name,
        "category_name": category_name,
        "description": recipe.description,
        "spice_options": _jsonable(recipe.spice_options),
        "is_sold_out": recipe.is_sold_out,
    }


def category_to_dict(category: Any, recipe_count: int) -> dict:
    """分类条目 + 这一类有几道菜。"""
    return {
        "id": category.id,
        "name": category.name,
        "recipe_count": recipe_count,
    }


class MenuQueryService:
    """把「查冰箱 / 查菜单」的组装和整形收在一处。

    ⚠️ 每个实例绑定一个 session —— 不要跨请求复用（连接会一直占着不放）。
       和 `mcp/server/tools.py` 里"每个工具自己组装 service"是同一个理由。
    """

    def __init__(self, session: Any) -> None:
        # SpaceService 要一个 CategoryRepository，那是"建家庭组时顺手建默认分类"用的。
        # 这里不建组，传进去只是满足依赖装配。
        self._space = SpaceService(SpaceRepository(session), CategoryRepository(session))
        self._fridge = FridgeService(FridgeRepository(session), self._space)
        self._category = CategoryService(CategoryRepository(session), self._space)
        self._recipe = RecipeService(
            RecipeRepository(session),
            self._space,
            self._category,
        )

    async def ensure_member(self, user: Any, space_id: int) -> None:
        """校验「这个人是不是这个家的成员」，不是就抛 BusinessError。

        ⭐ 为什么把这道校验也放在这里？
           因为**两个调用方都需要它，而且需要的是同一份规则**：
             · Agent 的工具每次执行前都要过（`space_id` 是客户端传的，不能信）；
             · AI 对话服务在**开始跑 Agent 之前**要先挡一次，
               这样越权请求会立刻返回明确的错误，而不是绕一圈工具才发现没权限。
           规则只有一份，就不会出现"这边拦住了、那边漏了"。
        """
        await self._space.ensure_member(space_id, user.id)

    async def fridge(
        self,
        user: Any,
        space_id: int,
        category: str | None = None,
        storage: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[dict], int]:
        """列冰箱食材。返回 (食材列表, 全组临期件数)。

        `expiring_count` 始终统计整个家庭组（不受筛选条件影响），
        这样"有 2 样快过期"这句提示在筛选前后都稳定。
        """
        rows, expiring_count = await self._fridge.list_items(
            user, space_id, category, storage, keyword
        )
        today = date.today()
        items = [fridge_item_to_dict(item, today) for item, _nickname in rows]
        return items, expiring_count

    async def expiring(self, user: Any, space_id: int, window: int) -> list[dict]:
        """列未来 `window` 天内要过期（含已过期）的食材，最急的排最前。

        ⚠️ 为什么取全量再在内存里筛？
           repo 只提供了"未来 N 天内的**计数**"，没有"未来 N 天内的**列表**"。
           为一个工具去改 repo 不划算，而一个家的食材量（几十条）内存筛毫无压力。
        """
        rows, _ = await self._fridge.list_items(user, space_id)
        today = date.today()
        deadline = today + timedelta(days=window)
        items = [
            fridge_item_to_dict(item, today)
            for item, _nickname in rows
            if item.expiry_date is not None and item.expiry_date <= deadline
        ]
        # 已过期（negative）自然排最前，模型转述时顺序就是对的
        items.sort(key=lambda entry: entry["days_left"])
        return items

    async def recipes(
        self,
        user: Any,
        space_id: int,
        category_id: int | None = None,
        keyword: str | None = None,
    ) -> list[dict]:
        """列菜谱。

        筛选用的 `category_id` 不额外校验归属：查询本身带着"必须是这个家庭组"
        的条件，传了别人家的 ID 也只会得到空列表。多查一次库换不来任何安全性。
        """
        rows = await self._recipe.list_recipes(user, space_id, category_id, keyword)
        return [recipe_to_dict(recipe, name) for recipe, _nickname, name in rows]

    async def categories(self, user: Any, space_id: int) -> list[dict]:
        """列分类（含每类几道菜）。"""
        rows = await self._category.list_categories(user, space_id)
        return [category_to_dict(category, count) for category, count in rows]
