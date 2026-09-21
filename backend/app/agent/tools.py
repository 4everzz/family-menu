"""Agent 能用的工具：声明（给模型看）+ 执行（真去查）。

⭐ 两条铁律：

1. **执行严格走 service 层**（`MenuQueryService`），不直接查库。
   工具是给模型开的入口，**绝不能变成绕过权限的后门**——
   `ensure_member` 那一道必须过。所以这里一个 SQL 都不写。

2. **工具失败不往外抛**。异常一律转成 `{"ok": false, "error": "人话"} `还给模型，
   让它自己决定怎么跟用户解释（"冰箱查不到，那我按常识给你说说"）。
   抛出去的话这一轮对话就整个废了——而用户可能只是想问个菜。

⭐ 一个刻意的区分：「工具坏了」和「查了但没有」不是一回事：
   · `{"ok": false}`          → 没权限、参数错、上游挂了（**异常**）
   · `{"ok": true, "found": false}` → 查通了，但权威数据源里没有这条（**正常结果**）
   混成一个的话，模型会对着一件正常的事跟用户道歉。

⭐ 工具数量刻意只有 5 个。**不是越多越好**——
   工具选择本身是个分类问题，候选越多越容易选错。
   这里只放"对话真的需要"的查询；所有写操作（记账、点菜）都不做工具，
   一律走前端的确认卡片，保持"模型只有提议权"这条边界。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.models.user import User
from app.services import nutrition_service
from app.services.menu_query_service import MenuQueryService, clamp_expiring_days

logger = logging.getLogger(__name__)

#: 单个工具最多返回多少条。
#: 为什么不全给？—— token 预算。一个家庭几十道菜、上百条食材全塞进上下文，
#: 既贵又容易把模型的注意力冲散。超出时明确告诉它"截断了，还有更多"，
#: 它可以让用户缩小范围再查。
MAX_TOOL_ITEMS = 50


@dataclass(frozen=True)
class ToolContext:
    """执行工具需要知道的"谁在问、问的是哪个家"。

    ⚠️ `space_id` 是**客户端传上来的**，不能直接信——
       工具内部走 service，service 里的 `ensure_member` 会把它验一遍
       （不是这家人就直接失败）。这里只是把它带过来。
    """

    session: Any
    user: User
    space_id: int | None


class ToolRunError(Exception):
    """工具执行失败（预期内的：没选家庭组、参数不对）。

    单独一个类型是为了和"程序写错了"区分开：这类错误的原因对用户有用，
    可以原样告诉模型；其它异常只回一句笼统提示，真实原因打到日志给开发看。
    """


# ============================================================================
# 参数小工具
# ============================================================================


def _to_int(value: Any) -> int | None:
    """把模型给的"数字"转成 int。它经常把数字写成字符串（`"3"`）。"""
    if isinstance(value, bool):  # bool 是 int 的子类，先挡掉
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> str | None:
    """把可选字符串参数规整一下：空串、空白、非字符串一律当"没传"。"""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _require_space(ctx: ToolContext) -> int:
    """取家庭组 ID，没选就报一句人话。

    这里不抛 BusinessError，是因为它不是"业务规则不满足"，而是
    "这次对话缺少一个参数"——模型拿到原因后可以追问用户"你想看哪个家庭组的？"
    """
    if ctx.space_id is None:
        raise ToolRunError(
            "还没有确定要查哪个家庭组。请先问用户想看哪个家（或让他在页面上选一个家）。"
        )
    return ctx.space_id


def _truncate(rows: list[dict], total_key: str) -> dict:
    """条目太多时截断，并如实告诉模型"还有更多"。"""
    if len(rows) <= MAX_TOOL_ITEMS:
        return {"count": len(rows), total_key: rows}
    return {
        "count": len(rows),
        "truncated": True,
        "note": f"共 {len(rows)} 条，这里只给了前 {MAX_TOOL_ITEMS} 条。需要看其它的话，让用户缩小范围再查。",
        total_key: rows[:MAX_TOOL_ITEMS],
    }


# ============================================================================
# 工具实现（都走 service 层）
# ============================================================================


async def _list_fridge_items(
    ctx: ToolContext,
    keyword: str | None = None,
    category: str | None = None,
    storage: str | None = None,
) -> dict:
    """查冰箱里有什么。"""
    space_id = _require_space(ctx)
    items, expiring_count = await MenuQueryService(ctx.session).fridge(
        ctx.user, space_id, _to_str(category), _to_str(storage), _to_str(keyword)
    )
    return {
        "ok": True,
        "expiring_count": expiring_count,
        "note": "days_left 为负表示已经过期了几天；is_expiring 为 true 表示快到期了。",
        **_truncate(items, "items"),
    }


async def _get_expiring_items(ctx: ToolContext, days: Any = 7) -> dict:
    """查快过期（含已过期）的食材。"""
    space_id = _require_space(ctx)
    window = clamp_expiring_days(days)
    items = await MenuQueryService(ctx.session).expiring(ctx.user, space_id, window)
    return {
        "ok": True,
        "within_days": window,
        "note": "已经过期的排在最前面（days_left 是负数）。",
        **_truncate(items, "items"),
    }


async def _list_recipes(
    ctx: ToolContext,
    keyword: str | None = None,
    category_id: Any = None,
) -> dict:
    """查菜单上有哪些菜。"""
    space_id = _require_space(ctx)
    recipes = await MenuQueryService(ctx.session).recipes(
        ctx.user, space_id, _to_int(category_id), _to_str(keyword)
    )
    return {"ok": True, **_truncate(recipes, "recipes")}


async def _list_categories(ctx: ToolContext) -> dict:
    """查菜单分类（含每类几道菜）。"""
    space_id = _require_space(ctx)
    categories = await MenuQueryService(ctx.session).categories(ctx.user, space_id)
    return {"ok": True, **_truncate(categories, "categories")}


async def _lookup_nutrition(ctx: ToolContext, dish_name: Any = None) -> dict:
    """查食物的热量基准值（走 MCP 外部数据源）。

    ⚠️ 这个工具不需要 `space_id` —— 热量是公共知识，不属于某个家庭。
       所以它**在这个项目里是唯一一个不经过权限校验的工具**，
       这也是刻意的：能查到的只是《中国食物成分表》里的公开数据。
    """
    name = _to_str(dish_name)
    if not name:
        raise ToolRunError("要查热量得给我一个具体的食物名，比如「鸡蛋」「大米」。")

    nutrition = await nutrition_service.lookup_food_nutrition(name)
    if nutrition is None:
        # ⭐ 「查了但没有」不是错误 —— 宁可让模型退回估算，也不要它以为工具坏了
        return {
            "ok": True,
            "found": False,
            "note": (
                f"权威数据源里没有「{name}」这条。请按你的常识估算热量，"
                "并在回复里说明这是估的。不要再换名字反复查。"
            ),
        }

    return {
        "ok": True,
        "found": True,
        "matched_name": nutrition.matched_name,
        "energy_kcal_per_100g": nutrition.energy_kcal_per_100g,
        "note": (
            "这是**食材本身**每 100 克的能量，不是成品菜。"
            "用户说的是家常菜时要按烹饪方式修正（红烧/糖醋约 1.1~1.3 倍，"
            "油炸约 1.5~2 倍，清蒸/水煮约 0.8~0.9 倍），修正过要标成估算的。"
        ),
    }


_HANDLERS: dict[str, Callable[..., Awaitable[dict]]] = {
    "list_fridge_items": _list_fridge_items,
    "get_expiring_items": _get_expiring_items,
    "list_recipes": _list_recipes,
    "list_categories": _list_categories,
    "lookup_nutrition": _lookup_nutrition,
}


# ============================================================================
# 工具声明（给模型看的 schema）
# ============================================================================
#
# ⚠️ 这里的 description 是**给模型读的，不是给同事读的**。
#    所以要写"什么时候该用它"，而不是"这个函数做了什么"——
#    模型靠这句话决定要不要调它。
#
# `space_id` 刻意**不作为参数暴露**：它是本次对话的上下文，由后端注入。
# 让模型自己传一个 ID 进来，等于给它一个越权试错的机会。

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_fridge_items",
            "description": (
                "查看当前家庭组冰箱里有什么食材。"
                "当用户问「冰箱里有什么」「还有没有白菜」「有什么能做的」时用这个。"
                "返回里带 days_left（还能放几天，负数是已过期）和 is_expiring 标记。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "按食材名或备注模糊搜索，例如「白菜」。不传就是全部。",
                    },
                    "category": {
                        "type": "string",
                        "description": "按食材分类筛选，例如「蔬菜」「肉蛋」。不传就是全部。",
                    },
                    "storage": {
                        "type": "string",
                        "description": "按存放位置筛选，例如「冷藏」「冷冻」「常温」。不传就是全部。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_expiring_items",
            "description": (
                "查看快要过期（或已经过期）的食材，最急的排在最前面。"
                "当用户问「什么快过期了」「有什么该赶紧吃」时用这个。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "往后看几天，默认 7 天。已过期的永远包含在内。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recipes",
            "description": (
                "查看当前家庭组菜单上有哪些菜（用户自己录的菜谱）。"
                "当用户问「菜单上有什么」「今天做什么菜」「有没有红烧肉」时用这个。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "按菜名模糊搜索，例如「排骨」。不传就是全部。",
                    },
                    "category_id": {
                        "type": "integer",
                        "description": "按分类 ID 筛选。想按分类筛时，先用 list_categories 拿到分类 ID。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": (
                "查看菜单有哪些分类（凉菜、热菜、汤羹…）以及每类有几道菜。"
                "用户的问题比较宽泛、需要先知道分类才能收敛时用这个。"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_nutrition",
            "description": (
                "查一种**食材**每 100 克的热量（权威数据源）。"
                "用户说要记某样吃的东西时，用它拿基准值再换算，比凭印象估准得多。"
                "⚠️ 传**主料名**，不要传家常菜名——数据源是食物成分表，"
                "只有食材没有成品菜（「红烧肉」查不到，「猪肉」查得到；"
                "「糖醋排骨」查不到，「排骨」查得到）。"
                "如果是食材本身（鸡蛋、牛奶、豆腐）就直接传它。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dish_name": {
                        "type": "string",
                        "description": (
                            "要查的**食材**名，例如「猪肉」「排骨」「鸡蛋」「豆腐」。"
                            "用户说的是家常菜时，传它的主料（红烧肉→猪肉、糖醋排骨→排骨）。"
                        ),
                    },
                },
                "required": ["dish_name"],
            },
        },
    },
]


# ============================================================================
# 执行入口
# ============================================================================


async def execute(name: str, raw_arguments: Any, ctx: ToolContext) -> dict:
    """执行一个工具，**永不抛异常**。

    返回的 dict 会被序列化成 JSON 塞回对话，所以里面的措辞是**给模型看的**：
    它读懂了才能决定下一步（继续查、还是告诉用户查不到）。
    """
    handler = _HANDLERS.get(name)
    if handler is None:
        # 模型偶尔会"发明"一个不存在的工具名。告诉它有哪些，让它重来。
        return {
            "ok": False,
            "error": f"没有名为 {name} 的工具。可用的有：{', '.join(_HANDLERS)}。",
        }

    arguments = parse_arguments(raw_arguments)
    if arguments is None:
        return {"ok": False, "error": "工具参数不是合法的 JSON 对象，请重新给一次。"}

    try:
        return await handler(ctx, **arguments)
    except ToolRunError as exc:
        # 预期内的失败：原因对用户有用，原样转述
        return {"ok": False, "error": str(exc)}
    except TypeError as exc:
        # 参数对不上（模型编了个不存在的参数名）——这类要让它自己纠正
        logger.info("工具参数不匹配 | tool=%s | %s", name, exc)
        return {"ok": False, "error": f"参数不对（{exc}）。请只使用声明里有的参数。"}
    except Exception as exc:  # noqa: BLE001 —— 工具失败不能炸掉整轮对话
        # 没预料到的：可能是权限不足、数据库抖动、MCP 挂了。
        # ⚠️ 真实原因只写日志，不回给模型——里面可能有表名、连接串。
        logger.warning("工具执行失败 | tool=%s | %s: %s", name, type(exc).__name__, exc)
        return {
            "ok": False,
            "error": "这个查询暂时没成功（可能是没有权限，或者服务出了点问题）。"
            "请如实告诉用户没查到，不要编数据。",
        }


def parse_arguments(raw: Any) -> dict | None:
    """把模型给的参数转成 dict。

    模型给的是 JSON **字符串**（不是对象），偶尔还会包一层 markdown 代码块，
    所以这里松一点：是 dict 直接用，是字符串就试着解析，都不行返回 None。
    """
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}  # 没传参数（比如无参工具），当空对象处理

    text = raw.strip()
    if not text:
        return {}

    # 偶尔会带上 ```json 围栏，剥掉
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def tool_names() -> list[str]:
    """可用工具名清单（测试和排查时用）。"""
    return list(_HANDLERS)
