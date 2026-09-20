"""MCP Server 的工具实现：把本项目已有的 service 包成 MCP 工具。

设计原则（这几条决定了这份代码长什么样）：

1. **薄**。工具函数只做三件事：拿参数 → 组装 service → 把结果压成纯字典。
   业务规则一行都不在这里重写——全都调 service 层已有的方法。
   这样做的好处很实在：MCP 工具和 App 接口走的是**同一套权限校验、同一套业务规则**，
   不会出现"App 里改不了的冰箱，通过 AI 客户端能改"这种越权口子。

2. **复用鉴权，不自己发明**。身份靠 JWT（和 App 完全一样的那张通行证），
   校验逻辑直接调 `decode_access_token` + `UserRepository.get_by_id`，
   再交给 service 层的 `ensure_member` 判"是不是这家人"。
   不自己在 SQL 里写"查成员表"——那就是第二份实现，两份规则迟早会分叉。

3. **错误不往外抛**。MCP 工具抛异常，客户端拿到的是一个协议层的报错，
   模型看不懂（它只看到 "Tool execution failed"），用户也看不到原因。
   所以这里一律把异常转成结构化的 `{"ok": false, "error": "..."}`，
   让模型能读懂"是因为你不是这个家的成员"并转述给用户。

4. **返回值是纯数据，不是 ORM 对象**。MCP 的返回要序列化成 JSON 传给客户端，
   SQLAlchemy 的模型对象带一堆内部状态（会话关联、懒加载引用），
   直接塞进去既序列化不了，也会在会话关闭后炸掉。
   所以统一过一道 `_clean()`，把字段挑出来。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import jwt

from app.core.database import AsyncSessionLocal
from app.core.exceptions import BusinessError
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.category_repo import CategoryRepository
from app.repositories.fridge_repo import FridgeRepository
from app.repositories.recipe_repo import RecipeRepository
from app.repositories.space_repo import SpaceRepository
from app.repositories.user_repo import UserRepository
from app.services.category_service import CategoryService
from app.services.fridge_service import EXPIRING_WITHIN_DAYS, FridgeService
from app.services.recipe_service import RecipeService
from app.services.space_service import SpaceService

# ============================================================================
# 鉴权
# ============================================================================


class ToolAuthError(Exception):
    """工具层的鉴权/业务失败。

    单独一个异常类型，是为了和"程序写错了"（KeyError、TypeError 之类）区分开：
    这类错误是**用户的输入问题**，应该原样把原因告诉模型；
    而程序错误应该给一句笼统的提示，同时把堆栈打到 stderr 给开发看。
    """


async def _resolve_user(session: Any, token: str) -> User:
    """把 MCP 工具收到的令牌换成用户对象。

    令牌格式和 App 完全一致（`create_access_token` 签发的那张），
    所以用户可以在 App 里登录一次，把令牌贴给 Claude Desktop 用——
    不需要为 MCP 单独做一套账号体系。
    """
    cleaned = (token or "").strip()
    # 容忍用户从 App 里复制时带上前缀（"Bearer xxx"）
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned.split(" ", 1)[1].strip()

    if not cleaned:
        raise ToolAuthError(
            "缺少访问令牌。请先在「小家智膳」App 里登录，"
            "把拿到的 token 作为参数传进来。"
        )

    try:
        payload = decode_access_token(cleaned)
    except jwt.ExpiredSignatureError as exc:
        raise ToolAuthError("访问令牌已过期，请在 App 里重新登录后复制新的令牌。") from exc
    except jwt.PyJWTError as exc:
        raise ToolAuthError("访问令牌无效，请确认复制完整、没有多余的空格。") from exc

    subject = payload.get("sub")
    if not subject:
        raise ToolAuthError("访问令牌无效（缺少用户标识）。")

    user = await UserRepository(session).get_by_id(int(subject))
    if user is None or not user.is_active:
        raise ToolAuthError("账号不存在或已停用。")
    return user


# ============================================================================
# 序列化
# ============================================================================

#: 只输出这些字段。为什么不用 `model.__dict__` 全量吐出去？
#:   模型看的是 token 预算——一个冰箱条目带上 space_id、created_by、
#:   created_at、updated_at 这些它对不上的内部字段，纯属浪费上下文；
#:   而且 created_by 这类内部主键泄漏出去也没有任何好处。
_FRIDGE_FIELDS = ("id", "name", "quantity", "unit", "category", "storage", "expiry_date", "note")
_RECIPE_FIELDS = ("id", "name", "category_name", "description", "spice_options", "is_sold_out")
_CATEGORY_FIELDS = ("id", "name", "recipe_count")


def _clean(obj: Any, fields: tuple[str, ...]) -> dict:
    """把 ORM 对象挑字段转成纯字典（值转成 JSON 友好的类型）。

    日期转成 ISO 字符串（`2026-09-20`），模型读起来比时间戳自然得多。
    """
    data: dict[str, Any] = {}
    for name in fields:
        if name == "category_name":
            # 分类名不存在模型上，是 service 从关联查询里带出来的，单独取
            continue
        value = getattr(obj, name, None)
        if isinstance(value, date):
            value = value.isoformat()
        data[name] = value
    return data


def _clean_fridge_item(item: Any, today: date) -> dict:
    """冰箱条目：额外算一个 `days_left`。

    为什么在服务端算好、而不是让模型自己拿 expiry_date 减今天？
    因为模型不知道"今天"是哪天（它的时间概念不可靠），
    让它算必然算错。这种确定的算术，服务端给结果最省事也最准。
    """
    data = _clean(item, _FRIDGE_FIELDS)
    if item.expiry_date is None:
        data["days_left"] = None
        data["is_expiring"] = False
    else:
        days_left = (item.expiry_date - today).days
        data["days_left"] = days_left
        data["is_expiring"] = days_left <= EXPIRING_WITHIN_DAYS
    return data


# ============================================================================
# 工具：家庭冰箱
# ============================================================================


async def list_fridge_items(
    token: str,
    space_id: int,
    category: str | None = None,
    storage: str | None = None,
    keyword: str | None = None,
) -> dict:
    """列出某个家庭组冰箱里的食材。

    Args:
        token: 访问令牌（在 App 里登录后获得）。
        space_id: 家庭组 ID。
        category: 按分类筛选（如"蔬菜"），不传就是全部。
        storage: 按存放位置筛选（如"冷藏""冷冻"），不传就是全部。
        keyword: 按食材名或备注模糊搜索。
    """
    async with AsyncSessionLocal() as session:
        user = await _resolve_user(session, token)
        service = _build_fridge_service(session)
        # service 内部会 ensure_member：不是这家人就抛 AppError，不会读到别人的数据
        rows, expiring_count = await service.list_items(
            user, space_id, category, storage, keyword
        )
        today = date.today()
        items = [_clean_fridge_item(item, today) for item, _nickname in rows]
        return {
            "ok": True,
            "space_id": space_id,
            "count": len(items),
            "expiring_count": expiring_count,
            "items": items,
        }


async def get_expiring_items(token: str, space_id: int, days: int = 7) -> dict:
    """列出即将过期（或已经过期）的食材。

    默认看未来 7 天，和 App 里"临期提醒"用的是同一个窗口。
    返回值里 `days_left` 为负数表示**已经过期**了几天。

    Args:
        token: 访问令牌。
        space_id: 家庭组 ID。
        days: 往后看几天，默认 7。已过期的永远会包含在内。
    """
    # 上限保护：模型可能传个 3650，那不是"临期"是"全库"
    window = max(1, min(int(days), 30))
    async with AsyncSessionLocal() as session:
        user = await _resolve_user(session, token)
        service = _build_fridge_service(session)
        # 关键词不传，取全家食材，再在内存里按保质期筛——
        # repo 只提供了"未来 N 天内"的计数，没有"未来 N 天内的列表"，
        # 为了一个工具去改 repo 不划算，而一个家的食材量（几十条）内存筛毫无压力。
        rows, _ = await service.list_items(user, space_id)
        today = date.today()
        deadline = today + timedelta(days=window)
        items = [
            _clean_fridge_item(item, today)
            for item, _nickname in rows
            if item.expiry_date is not None and item.expiry_date <= deadline
        ]
        # 最急的排前面：已过期（负数）自然排到最前，模型转述时顺序就是对的
        items.sort(key=lambda entry: entry["days_left"])
        return {
            "ok": True,
            "space_id": space_id,
            "within_days": window,
            "count": len(items),
            "items": items,
        }


# ============================================================================
# 工具：菜单
# ============================================================================


async def list_recipes(
    token: str,
    space_id: int,
    category_id: int | None = None,
    keyword: str | None = None,
) -> dict:
    """列出某个家庭组的菜谱（菜单里的菜）。

    Args:
        token: 访问令牌。
        space_id: 家庭组 ID。
        category_id: 按分类 ID 筛选，不传就是全部。
        keyword: 按菜名模糊搜索。
    """
    async with AsyncSessionLocal() as session:
        user = await _resolve_user(session, token)
        service = _build_recipe_service(session)
        rows = await service.list_recipes(user, space_id, category_id, keyword)
        recipes: list[dict] = []
        for recipe, _nickname, category_name in rows:
            data = _clean(recipe, _RECIPE_FIELDS)
            data["category_name"] = category_name
            recipes.append(data)
        return {
            "ok": True,
            "space_id": space_id,
            "count": len(recipes),
            "recipes": recipes,
        }


async def list_categories(token: str, space_id: int) -> dict:
    """列出某个家庭组的菜单分类（含每类有几道菜）。

    用户问"冰箱里有什么"或"这周吃什么"时，先拿到分类清单能帮模型
    把宽泛的问题收敛成具体的筛选条件。

    Args:
        token: 访问令牌。
        space_id: 家庭组 ID。
    """
    async with AsyncSessionLocal() as session:
        user = await _resolve_user(session, token)
        service = _build_category_service(session)
        rows = await service.list_categories(user, space_id)
        categories: list[dict] = []
        for category, recipe_count in rows:
            data = _clean(category, _CATEGORY_FIELDS)
            data["recipe_count"] = recipe_count
            categories.append(data)
        return {
            "ok": True,
            "space_id": space_id,
            "count": len(categories),
            "categories": categories,
        }


# ============================================================================
# service 组装
# ============================================================================
#
# 每个工具自己组装需要的 service，而不是共用一个全局的。
# 原因：service 绑定在 session 上（构造函数第一个参数），而 session 是每个工具调用
# 开一个、用完就关。共用一个跨调用的 service 就等于让一个 session 活很久，
# 连接一直占着不放，且并发调用会互相干扰。


def _build_space_service(session: Any) -> SpaceService:
    """组装家庭组服务。

    SpaceService 构造要一个 CategoryRepository，那是"建家庭组时顺手建默认分类"用的。
    这里的工具都不建组，传进去只是满足依赖装配，不会被调用。
    """
    return SpaceService(SpaceRepository(session), CategoryRepository(session))


def _build_fridge_service(session: Any) -> FridgeService:
    return FridgeService(FridgeRepository(session), _build_space_service(session))


def _build_category_service(session: Any) -> CategoryService:
    return CategoryService(CategoryRepository(session), _build_space_service(session))


def _build_recipe_service(session: Any) -> RecipeService:
    return RecipeService(
        RecipeRepository(session),
        _build_space_service(session),
        _build_category_service(session),
    )


# ============================================================================
# 错误归一化
# ============================================================================


def describe_error(error: Exception) -> str:
    """把异常翻译成模型和用户都能读懂的一句话。

    分三类对待：
      · `ToolAuthError` / `BusinessError`——**预期内的失败**（令牌过期、不是这家人、
        家庭组不存在）。原因对用户有用，原样转述。
      · 其它异常——**没预料到的**（数据库连不上、代码写错）。给出笼统提示，
        真实原因由调用方打到 stderr 给开发看，**不能回给模型**——
        里面可能带连接串、表名这类不该外泄的信息。
    """
    if isinstance(error, (ToolAuthError, BusinessError)):
        return str(error)
    return "查询失败：服务内部出错了，请稍后再试。"
