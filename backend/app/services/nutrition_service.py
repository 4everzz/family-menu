"""营养数据服务：把"热量"从"大模型估的"变成"查出来的"。

═══════════════════════════════════════════════════════════════════════
⭐ 解决的问题（真实缺陷，不是为了用 MCP 而用 MCP）

   改造前：ai_chat_service 的 prompt 里写着"你按常识估一个热量"。
           → 同一个「红烧肉」，今天估 400、明天估 520。
           → **不可复现、不可追溯**，用户也不知道这个数是怎么来的。

   改造后：接 MCP 查《中国食物成分表》，热量是**查出来的**，
           并且**如实标注数据来源**。查不到的才退化成估算。

═══════════════════════════════════════════════════════════════════════
⭐ 两级策略（本文件的核心）

   cn-food-mcp 是**食材成分表**，不是菜谱库：
     ·「排骨」「豆腐」「鸡蛋(白皮)」→ ✅ 查得到
     ·「红烧肉」「土豆炖牛肉」       → ❌ 查不到（那是烹饪后的复合菜）

   所以设计成两级：

     第一级（查）：从菜名里提取主料 → MCP search_food → 命中了就拿每 100g 能量
     第二级（估）：没命中 → 交给大模型按常识 + 烹饪方式修正

   ⚠️ 但**第二级的活不在这个文件里做**。
      为什么？因为"按烹饪方式修正"需要大模型参与，
      而大模型调用在 ai_chat_service 里（prompt 已经组好了）。
      这个文件只负责**把查到的权威值交给它做参考**。

   → 所以本文件的职责边界是：
       「给定一个菜名，尽量查出权威的每 100g 热量」。
       「查到了怎么用、没查到怎么估」是 ai_chat_service 的事。

═══════════════════════════════════════════════════════════════════════
⭐ source 字段（可信度分级）

   面试话术的落点。每份热量都带一个来源标记：

     mcp_exact    —— MCP 精确命中（食材名对上了）        → 是"查"的
     mcp_derived  —— MCP 基准 + AI 按烹饪方式修正        → 有依据的推算
     llm_estimate —— 纯 AI 估算（MCP 没命中 / 没开启）    → 是"猜"的

   ⚠️ 措辞要诚实：这叫"**降低**幻觉并让用户能分辨"，
     不是"**避免**幻觉"——因为第二级仍然有大模型参与，
     而且第一级也可能匹配到近似食材（搜"排骨"可能命中"猪大排"）。
     面试官追问时坦白这一点，反而比说满更加分。
═══════════════════════════════════════════════════════════════════════
"""

import json
import logging
from dataclasses import dataclass

from app.core.config import settings
from app.core.redis_client import get_client
from app.mcp import gateway

logger = logging.getLogger(__name__)

# 来源标记（字符串常量，前端和测试都用这几个值）
SOURCE_MCP_EXACT = "mcp_exact"
SOURCE_MCP_DERIVED = "mcp_derived"
SOURCE_LLM_ESTIMATE = "llm_estimate"

#: MCP Server 与工具名（业务层不该记这些，但改一次也就这一处）
_SERVER = "food"
_TOOL_SEARCH = "search_food"
_TOOL_DETAIL = "get_nutrition"

#: 缓存有效期（秒）。营养数据几乎不变，给一天足够。
#: 为什么还要 TTL？—— 万一上游数据修订了，缓存不该永远压着旧值。
_CACHE_TTL = 60 * 60 * 24
#: 缓存 key 前缀。带 `fm:` 是为了不跟 Dify 之类的同库应用撞名
_CACHE_PREFIX = "fm:nutrition:v1:"

#: 超过这个长度不往缓存塞（防个别异常响应把 value 撑爆）
_MAX_CACHE_VALUE = 4096

#: 可信查询的最短长度。
#:
#: ⚠️ 这条是**用真实事故换来的**：
#:   单字查询（"肉"）在成分表里能匹配到几十种东西，
#:   而"名字最短的那个"往往是冷门特例（蚌肉、蛇肉…），不是用户想说的猪肉。
#:   所以单字候选词一律不信，直接退化成 AI 估算。
_MIN_RELIABLE_QUERY_LEN = 2

#: 每 100g 能量的合理上限（千卡）。
#:
#: 纯油脂是天花板（约 899 kcal/100g），超过这个数的必然是脏数据或单位错。
#: 给到 1000 留一点余量。
MAX_REASONABLE_KCAL_PER_100G = 1000.0


@dataclass
class FoodNutrition:
    """一道菜查出来的营养信息。"""

    #: 命中的食材名（可能和用户说的菜名不完全一样，如"排骨"→"猪小排"）
    matched_name: str
    #: 每 100g 能量（千卡）
    energy_kcal_per_100g: float
    #: 数据来源，见文件头的 source 分级
    source: str
    #: 上游食物 ID，留着做追溯（"这个数是谁给的"）
    food_id: int | None = None


# ---------------------------------------------------------------------------
# 菜名 → 食材名的归一化
# ---------------------------------------------------------------------------

#: 去掉这些"烹饪方式/形态"词，剩下的更可能是能在成分表里查到的食材名。
#:
#: ⚠️ 这是**启发式**，不是精确的语义理解。说人话就是"猜得比较准的字符串处理"。
#:    为什么不上分词库？—— 加一个依赖、还得维护词典，收益不如这几行明显。
#:    真要做准，应该让大模型直接输出"主料"字段（prompt 里已经在这么要求了）。
_COOKING_WORDS = (
    "红烧", "清蒸", "水煮", "油炸", "油焖", "爆炒", "小炒", "干煸",
    "凉拌", "卤", "烤", "煎", "炖", "煮", "蒸", "炒", "焖", "拌",
    "汤", "羹", "粥", "面", "饭", "粉", "丝", "片", "块", "丁",
)

#: 这些字出现在菜名里，说明是复合菜 → 拆开取主料更容易命中
_SPLIT_CHARS = ("炖", "炒", "烧", "蒸", "煮", "焖", "拌", "配", "加")

#: 单字候选词的黑名单。
#:
#: ⚠️ 为什么要专门列这个？
#:   拆"红烧肉"会得到 ["红", "肉"]——"红"这种词拿去 search_food
#:   会命中一堆莫名其妙的东西（"红糖""红辣椒"…），把结果带偏。
#:   单字里真正能当食材名的很少，与其猜不如直接不试。
#:
#: 注意"清""香""酥""脆""嫩"这类**烹饪形容词**也要挡——
#: 它们是从"清蒸鲈鱼"这类菜名里切剩下的（"蒸"是切分点，"清"会剩下）。
_IGNORED_SINGLE_CHARS = frozenset(
    "红白黄绿黑紫金木水火土香甜酸苦辣咸鲜老嫩大小多少干湿生熟新旧"
    "清酥脆软硬糯滑爽麻辣烫卤糟醉腌拌炒炸煎烤蒸煮炖焖烧烩煨汆涮"
)

#: 只表示"某物的一部分"的后缀词。
#:
#: ⚠️ 真实事故：`search_food("鸡蛋")` 返回
#:    "鸡蛋白 60 / 鸡蛋黄 328 / 鸡蛋(白皮) 138 / 鸡蛋(红皮) 156"——
#:    **没有一条叫"鸡蛋"**。按"前缀命中取最短"会挑中「鸡蛋白」60 kcal，
#:    但用户说"鸡蛋"基本都指**整蛋**（138）。
#:
#: 所以：前缀命中时，如果结果名是在候选词后面接了一个"部分词"，
#:       那它大概率不是用户要的 → 跳过。
_PART_SUFFIX_WORDS = (
    "白", "黄", "皮", "壳", "清", "油", "粉", "干", "酱", "汁", "末", "丝", "片",
)

#: 常见的"部位 / 形态"后缀。
#:
#: ⚠️ 用途：有些菜名里**没有任何连接词**，但有这些后缀，
#:    而且**后缀本身就是很好的查询词**。
#:    例：「糖醋排骨」→ 没有"炖/炒/烧"，切不开；
#:        但"排骨"是标准食材名，直接拿去查就命中。
#:    如果不做这一步，「糖醋排骨」会整个词拿去查 → 查不到 → 白白退化。
_MEAT_PART_SUFFIXES = (
    "排骨", "五花肉", "里脊", "鸡翅", "鸡腿", "鸡胸", "牛腩", "培根",
    "肉末", "肉丝", "肉片", "鸡爪", "猪蹄", "肥肠", "牛腱", "鸡胗", "鸭腿",
)


def _is_usable_candidate(word: str) -> bool:
    """判断一个候选词值不值得拿去搜。

    ⚠️ 这里**是启发式，不是语义理解**。目的很朴素：
       别把明显查不出东西的词（单个"红"、空串）浪费成一次 MCP 往返。

    规则：
      · 空串不要
      · 单个字：只有不在黑名单里才要（"米""鱼""肉"值得试；"红""白"不值得）
      · 两个字以上：要
    """
    if not word:
        return False
    if len(word) == 1:
        return word not in _IGNORED_SINGLE_CHARS
    return True


def normalize_dish_name(dish_name: str) -> list[str]:
    """把一个菜名拆成若干"可能查得到"的候选食材名。

    返回按优先级排的候选列表（越靠前越可能是能在成分表里查到的食材）。

    例：
      "红烧肉"       → ["肉", "红烧肉"]        （"红"被黑名单挡掉）
      "土豆炖牛肉"   → ["土豆", "牛肉", "土豆炖牛肉"]
      "鸡蛋(白皮)"   → ["鸡蛋(白皮)", "鸡蛋"]
    """
    name = (dish_name or "").strip()
    if not name:
        return []

    candidates: list[str] = []

    # ① 按"炖/炒/烧"这类连接词切开——复合菜的主料通常在两边
    parts = [name]
    for ch in _SPLIT_CHARS:
        next_parts: list[str] = []
        for part in parts:
            next_parts.extend(p for p in part.split(ch) if p)
        parts = next_parts
    if len(parts) > 1:
        # 多段时优先取"更像食材"的：长的在前
        # ⚠️ 这里**不去烹饪词**——因为切开之后各段本身就不含连接词了，
        #    再去一次反而会把"白菜"变成"菜"这种更差的结果。
        for part in sorted(parts, key=len, reverse=True):
            cleaned = part.strip()
            if _is_usable_candidate(cleaned) and cleaned not in candidates:
                candidates.append(cleaned)

    # ② 常见部位后缀（"糖醋排骨"→"排骨"、"黑椒牛腩"→"牛腩"）
    #
    #    ⚠️ 放在整体去烹饪词**之前**——因为这些菜名里没有连接词，
    #       整体去词也去不掉（"排骨"不在 _COOKING_WORDS 里），
    #       只有主动识别后缀才能救回来。
    for suffix in _MEAT_PART_SUFFIXES:
        if suffix in name and name != suffix:
            if suffix not in candidates:
                candidates.append(suffix)
            break  # 命中一个就够，别把整个列表都塞进去

    # ③ 整体去掉烹饪词（"红烧肉"→"肉"）
    stripped = _strip_cooking_words(name)
    if _is_usable_candidate(stripped) and stripped not in candidates:
        candidates.append(stripped)

    # ④ 原词兜底——有些菜名本身就是标准食材名（"豆腐""鸡蛋(白皮)"）
    if name not in candidates:
        candidates.append(name)

    # ⑤ 括号前的部分（"鸡蛋(白皮)" → "鸡蛋"）
    if "(" in name:
        base = name.split("(")[0].strip()
        if _is_usable_candidate(base) and base not in candidates:
            candidates.append(base)

    return candidates


def _strip_cooking_words(text: str) -> str:
    """去掉烹饪方式/形态词。从左往右扫，一次去掉一个。"""
    result = text
    changed = True
    while changed and result:
        changed = False
        for word in _COOKING_WORDS:
            if result.startswith(word) and len(result) > len(word):
                result = result[len(word) :]
                changed = True
                break
    return result


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------


def _cache_key(dish_name: str) -> str:
    return f"{_CACHE_PREFIX}{dish_name.strip()}"


def _cache_get(dish_name: str) -> FoodNutrition | None:
    """读缓存。读不到 / Redis 挂了 → None（回源查）。"""
    # ⚠️ `get_client()` 本身也要包在 try 里。
    #    它设计上"连不上就返回 None"，但那是它自己的约定；
    #    缓存是**纯优化**，任何一环出意外都不该把查询带崩。
    #    把取客户端和读数据都收进同一个 try，是这个函数唯一的正确写法。
    try:
        client = get_client()
        if client is None:
            return None
        raw = client.get(_cache_key(dish_name))
    except Exception as exc:
        logger.debug("营养缓存读取失败（忽略，回源查询）：%s", exc)
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        return FoodNutrition(
            matched_name=payload["matched_name"],
            energy_kcal_per_100g=float(payload["energy_kcal_per_100g"]),
            source=payload["source"],
            food_id=payload.get("food_id"),
        )
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        # 缓存内容坏了（比如手改了 Redis）→ 当作没有，别把脏数据喂给业务
        logger.warning("营养缓存内容异常，忽略：%s", exc)
        return None


def _cache_set(dish_name: str, nutrition: FoodNutrition) -> None:
    """写缓存。写失败 / Redis 挂了 → 静默放弃（不影响这次请求）。"""
    try:
        client = get_client()
        if client is None:
            return
        payload = json.dumps(
            {
                "matched_name": nutrition.matched_name,
                "energy_kcal_per_100g": nutrition.energy_kcal_per_100g,
                "source": nutrition.source,
                "food_id": nutrition.food_id,
            },
            ensure_ascii=False,
        )
        if len(payload) > _MAX_CACHE_VALUE:
            return
        client.setex(_cache_key(dish_name), _CACHE_TTL, payload)
    except Exception as exc:
        # 写缓存失败**绝不能**影响这次请求——数据已经查到了，
        # 只是下次还得再查一遍而已。
        logger.debug("营养缓存写入失败（忽略）：%s", exc)


# ---------------------------------------------------------------------------
# 第一级：查 MCP
# ---------------------------------------------------------------------------


def _pick_best_food(foods: list[dict], wanted: str) -> dict | None:
    """从搜索结果里挑一个最合适的。

    ⚠️ 这一步是整个查询里**最容易出错**的地方，必须保守。

    ── 踩过的坑（真实事故）──────────────────────────────
    `search_food("肉")` 返回"蚌肉、猪肉、牛肉、鸡肉…"，
    按"名字最短优先"会挑中 **「蚌肉」71 kcal** ——
    而「红烧肉」应该是 400+，直接把用户的热量算成六分之一。

    同类事故：`search_food("鸡蛋")` 挑中 **「鸡蛋白」60 kcal**，
    但整蛋应该是 138。

    ── 教训 ────────────────────────────────────────────
    泛化的词（尤其单字"肉""蛋""鱼"）拿去搜，**返回的最短名字往往不是用户想要的**。
    与其"猜一个"，不如**不猜**——返回 None 让业务层退化成 AI 估算。
    估算虽然不够准，但至少不会给出一个离谱的确定值。

    ── 现在的规则（保守优先）────────────────────────────
      · 名字**完全等于**候选词          → 直接采用（"豆腐"→"豆腐"）
      · 候选词是**两个及以上**字，
        且结果名以它**开头**            → 采用（"鲈鱼"→"鲈鱼(鲜)"）
      · 候选词是**单字**                 → **一律不采用**（宁可退化）
      · 其余情况                         → 不采用
    """
    if not foods:
        return None

    # 单字候选词不信——"肉""蛋""鱼"搜出来最短的那个基本都是错的特例
    if len(wanted) < _MIN_RELIABLE_QUERY_LEN:
        return None

    valid = [f for f in foods if _to_float(f.get("energy_kcal")) is not None]
    if not valid:
        return None

    # ① 完全命中，最可信
    for item in valid:
        if str(item.get("name") or "") == wanted:
            return item

    # ② 前缀命中。分两档取，因为"哪一档更对"是实测出来的：
    #
    #    档 1：`鸡蛋(白皮)` / `猪肉(肥瘦)` 这种**带括号的规范名**——
    #          成分表里"整体食材"通常就是这种写法，最贴近用户说的。
    #    档 2：普通前缀（`鲈鱼` 之于 `鲈鱼(鲜)`），取最短的。
    #
    #    ⚠️ 必须排除"某物的一部分"：search_food("鸡蛋") 也返回
    #       "鸡蛋白 60 / 鸡蛋黄 328"——按长度取最短会挑中「鸡蛋白」，
    #       而用户说"鸡蛋"指的是整蛋。所以带"部分词"的直接跳过。
    bracketed = []
    plain = []
    for item in valid:
        name = str(item.get("name") or "")
        if not name.startswith(wanted):
            continue
        tail = name[len(wanted) :]
        if tail and any(tail.startswith(word) for word in _PART_SUFFIX_WORDS):
            continue  # "鸡蛋"→"鸡蛋白"，是部位不是整体
        if tail.startswith("("):
            bracketed.append(item)
        elif tail:
            plain.append(item)

    # 带括号的优先（更可能是"整体食材"的规范条目）
    for bucket in (bracketed, plain):
        if bucket:
            return min(bucket, key=lambda f: len(str(f.get("name") or "")))

    # ③ 都不像 → 不猜
    return None


def _to_float(value: object) -> float | None:
    """把上游给的值转成数字，容忍字符串形式的数字。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


async def _query_mcp(dish_name: str) -> FoodNutrition | None:
    """走 MCP 查一次。查不到 / MCP 不可用 → None（交给第二级）。"""
    for candidate in normalize_dish_name(dish_name):
        result = await gateway.call_tool(_SERVER, _TOOL_SEARCH, {"query": candidate})
        if not result.ok:
            # MCP 本身不可用（没开 / 超时 / 挂了）→ 别继续试别的候选词了，
            # 试多少次都一样。直接交给第二级。
            logger.info("MCP 查询不可用，热量将退化为估算 | dish=%s | %s", dish_name, result.error)
            return None

        foods = result.data.get("foods")
        if not isinstance(foods, list) or not foods:
            continue  # 这个候选词没结果，试下一个

        best = _pick_best_food(foods, candidate)
        if best is None:
            continue

        energy = _to_float(best.get("energy_kcal"))
        if energy is None or not (0 < energy <= MAX_REASONABLE_KCAL_PER_100G):
            continue

        # ⚠️ 最后一道闸：结果名和候选词的**语义距离**检查。
        #
        #    真实事故：搜"肉"命中"蚌肉"71 kcal——结果名里确实含"肉"，
        #    前缀规则也拦不住（"蚌肉"不以"肉"开头，靠完全命中/前缀都过不了，
        #    但现在加了后缀识别后要防另一个方向的问题）。
        #
        #    规则很朴素：**结果名里必须真的含候选词**。
        #    "蚌肉"不含"肉"吗？含。所以这条拦不住它——
        #    真正拦住它的是上面"单字候选词不信"（_MIN_RELIABLE_QUERY_LEN）。
        #    这里只做最基本的兜底：结果名不能跟候选词完全不搭边。
        matched_name = str(best.get("name") or "")
        if candidate not in matched_name:
            continue

        food_id = best.get("id")
        return FoodNutrition(
            matched_name=matched_name or candidate,
            energy_kcal_per_100g=energy,
            source=SOURCE_MCP_EXACT,
            food_id=int(food_id) if isinstance(food_id, int) else None,
        )

    return None


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------


async def lookup_food_nutrition(dish_name: str) -> FoodNutrition | None:
    """查一道菜的权威营养数据。

    返回 None 表示"查不到"——调用方（ai_chat_service）据此决定：
      · 拿到了 → 把每 100g 热量喂给模型做换算依据，source 标记为"查到的"
      · None   → 让模型按常识估，source 标记为"估的"

    ⚠️ **本函数绝不抛异常**。MCP 是外部依赖，它的问题不该冒泡到接口层。
    """
    name = (dish_name or "").strip()
    if not name:
        return None

    # 缓存优先——营养数据几乎不变，同一道菜没必要反复起子进程
    cached = _cache_get(name)
    if cached is not None:
        logger.debug("营养缓存命中：%s", name)
        return cached

    if not settings.mcp_enabled:
        # MCP 没开就完全不查。这是"默认不影响现有行为"的保证点之一：
        # 关闭时这里连子进程都不会起。
        return None

    try:
        nutrition = await _query_mcp(name)
    except Exception as exc:
        # gateway 已经吃掉大部分异常了，这里是最后一道保险
        logger.warning("营养查询异常（将退化为估算）：%s | %s", name, exc)
        return None

    if nutrition is not None:
        _cache_set(name, nutrition)
    return nutrition
