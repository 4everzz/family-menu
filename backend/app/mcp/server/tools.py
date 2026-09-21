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

⭐ 5. **「查什么、怎么整形」不在这里**——那是 `MenuQueryService` 的活。
   理由：App 自己的 Agent（`app/agent/tools.py`）要问同样几个问题、
   要同样形状的答案。两边各写一份，早晚会出现
   "App 里说还能放 5 天、MCP 那边算成 6 天"这种极难发现的不一致。
   **协议可以有两套，数据口径只能有一套。**

   所以这个文件剩下的职责只有一个：**怎么用 MCP 的方式把数据暴露出去**
   （收 token 做跨进程鉴权、包 `ok/error` 信封）。
"""

from __future__ import annotations

from typing import Any

import jwt

from app.core.database import AsyncSessionLocal
from app.core.exceptions import BusinessError
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.services.menu_query_service import MenuQueryService, clamp_expiring_days

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
        # service 内部会 ensure_member：不是这家人就抛 BusinessError，不会读到别人的数据
        items, expiring_count = await MenuQueryService(session).fridge(
            user, space_id, category, storage, keyword
        )
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
    window = clamp_expiring_days(days)
    async with AsyncSessionLocal() as session:
        user = await _resolve_user(session, token)
        items = await MenuQueryService(session).expiring(user, space_id, window)
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
        recipes = await MenuQueryService(session).recipes(user, space_id, category_id, keyword)
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
        categories = await MenuQueryService(session).categories(user, space_id)
        return {
            "ok": True,
            "space_id": space_id,
            "count": len(categories),
            "categories": categories,
        }


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
