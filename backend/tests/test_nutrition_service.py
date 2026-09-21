"""营养查询服务测试。

这个服务是整个 MCP 集成里**最容易出错**的一环，因为它要做三件互相拉扯的事：
    ① 尽量查出真实数据（不然接 MCP 就没意义）；
    ② 但查不准的时候宁可**不查**（退化成 AI 估算）；
    ③ 结果缓存起来，别每次都去起 npx。

所以测试的重点不是"happy path 能返回数字"，而是**边界与降级**：

  · 菜名拆解会不会拆出垃圾候选词（"红烧肉" → "红"）
  · 搜索结果选错了怎么办（真实事故：红烧肉 → 蚌肉 71 kcal）
  · MCP 挂了会不会把业务带崩（必须返回 None，不能抛）
  · 缓存命中时会不会**跳过一次查询**（不是"结果一样"，而是真的没调）

⚠️ 这些用例都**不打桩 MCP 子进程**，而是直接测纯函数 + 用假数据打桩 gateway，
   因为这里要验证的是"决策逻辑"，不是"能不能起 npx"（那个在 gateway 测试里）。
"""

import re
from datetime import date

import pytest

from app.core.config import settings
from app.services import nutrition_service as ns


# ============================================================================
# 菜名拆解
# ============================================================================


class TestNormalizeDishName:
    """>= 拆菜名。这一层错了，后面全错，所以用例给得最密。"""

    def test_composite_dish_splits_into_ingredients(self):
        """复合菜拆出两边主料。"""
        result = ns.normalize_dish_name("土豆炖牛肉")
        assert "土豆" in result
        assert "牛肉" in result

    def test_meat_part_suffix_recovered(self):
        """部位词后缀能救回来——这些菜名里没有连接词，整体去烹饪词也去不掉。"""
        assert "排骨" in ns.normalize_dish_name("糖醋排骨")
        assert "牛腩" in ns.normalize_dish_name("黑椒牛腩")

    def test_cooking_word_only_stripped(self):
        """整体去烹饪词："红烧肉" → "肉"。"""
        assert "肉" in ns.normalize_dish_name("红烧肉")

    def test_single_char_from_cooking_word_is_filtered(self):
        """⚠️ 回归："红烧肉" 曾经拆出垃圾候选词 "红"。

        根因是按连接词切分后再去烹饪词，导致 "红烧" 断成 "红"。
        现在单字黑名单挡住了——"红" 在 _IGNORED_SINGLE_CHARS 里。
        """
        result = ns.normalize_dish_name("红烧肉")
        assert "红" not in result, f"拆出了垃圾候选词：{result}"

    def test_plain_ingredient_stays_intact(self):
        """本身就是标准食材名的不该被拆坏。"""
        assert ns.normalize_dish_name("豆腐") == ["豆腐"]
        assert "鸡蛋" in ns.normalize_dish_name("鸡蛋")

    def test_bracketed_name_yields_base(self):
        """"鸡蛋(白皮)" 要能给出 "鸡蛋" 这个更能搜到的形式。"""
        result = ns.normalize_dish_name("鸡蛋(白皮)")
        assert "鸡蛋" in result

    def test_empty_input(self):
        assert ns.normalize_dish_name("") == []
        assert ns.normalize_dish_name("   ") == []
        assert ns.normalize_dish_name(None) == []

    def test_no_duplicate_candidates(self):
        """候选词不能重复（重复就是白跑一次查询）。"""
        for dish in ("红烧肉", "土豆炖牛肉", "清蒸鲈鱼", "鸡蛋(白皮)"):
            result = ns.normalize_dish_name(dish)
            assert len(result) == len(set(result)), f"{dish} 产生重复候选：{result}"


# ============================================================================
# 搜索结果挑选
# ============================================================================


class TestPickBestFood:
    """挑结果。**这里每个用例都对应一次真实的数据事故。**"""

    def test_exact_match_wins(self):
        foods = [{"name": "豆腐", "energy_kcal": 81}, {"name": "豆腐皮", "energy_kcal": 409}]
        assert ns._pick_best_food(foods, "豆腐")["name"] == "豆腐"

    def test_single_char_query_is_refused(self):
        """⚠️ 真实事故回归：单字候选词一律不信。

        `search_food("肉")` 返回蚌肉/猪肉/牛肉/鸡肉…，
        一旦挑中「蚌肉」71 kcal，红烧肉（应为 400+）就被算成六分之一。
        现在的策略是：**宁可查不到，也不给离谱的确定值。**
        """
        foods = [
            {"name": "蚌肉", "energy_kcal": 71},
            {"name": "猪肉", "energy_kcal": 395},
            {"name": "牛肉", "energy_kcal": 125},
        ]
        assert ns._pick_best_food(foods, "肉") is None

    def test_part_suffix_excluded(self):
        """⚠️ 真实事故回归：`鸡蛋` 不该挑中 `鸡蛋白`。

        search_food("鸡蛋") 的结果里没有叫"鸡蛋"的，只有
        鸡蛋白 / 鸡蛋黄 / 鸡蛋(白皮) / 鸡蛋(红皮)。
        按"名字最短优先"会挑中鸡蛋白(60)，而整蛋是 138。
        """
        foods = [
            {"name": "鸡蛋白", "energy_kcal": 60},
            {"name": "鸡蛋黄", "energy_kcal": 328},
            {"name": "鸡蛋(白皮)", "energy_kcal": 138},
            {"name": "鸡蛋(红皮)", "energy_kcal": 156},
        ]
        picked = ns._pick_best_food(foods, "鸡蛋")
        assert picked is not None
        assert picked["name"] == "鸡蛋(白皮)", "应当优先带括号的规范名，而不是部位词"

    def test_bracketed_preferred_over_plain(self):
        """带括号的规范名（更像"整体食材"条目）优先于普通前缀。"""
        foods = [
            {"name": "大米粥", "energy_kcal": 46},
            {"name": "大米(粳米)", "energy_kcal": 346},
        ]
        assert ns._pick_best_food(foods, "大米")["name"] == "大米(粳米)"

    def test_generic_bracket_marker_wins_over_shortest(self):
        """⭐ 真实事故（2026-09-21）：`猪肉` 挑中了「猪肉(肥)」816 kcal。

        `猪肉(肥)` 只有 6 个字符，比 `猪肉(瘦)`/`猪肉(肥,瘦)` 都短，
        于是被"取最短名"选中——把「红烧肉 500g」估成了 2120 kcal（实际约 500~800）。

        括号里是**并列词**（`肥,瘦`）是成分表的"整体/代表值"写法，
        这个**结构性信号**必须优先于"名字长度"。
        """
        foods = [
            {"name": "猪肉(肥)", "energy_kcal": 816},
            {"name": "猪肉(瘦)", "energy_kcal": 143},
            {"name": "猪肉(肥,瘦)", "energy_kcal": 395},
        ]
        picked = ns._pick_best_food(foods, "猪肉")
        assert picked is not None
        assert picked["name"] == "猪肉(肥,瘦)", "应当优先'整体代表值'，而不是最短名"

    def test_generic_marker_result_is_order_independent(self):
        """多个通用标记同时出现时，按标记优先级取，**不依赖上游返回的顺序**。

        ⚠️ 如果实现写成"遍历候选、谁先碰到谁赢"，结果就会随数据源排序抖动——
        同样的查询今天返回 395、明天返回别的。这种不确定性最难查。
        """
        foods = [
            {"name": "牛肉(鲜)", "energy_kcal": 100},
            {"name": "牛肉(肥,瘦)", "energy_kcal": 190},
        ]
        assert ns._pick_best_food(foods, "牛肉")["name"] == "牛肉(肥,瘦)"
        assert ns._pick_best_food(list(reversed(foods)), "牛肉")["name"] == "牛肉(肥,瘦)"

    def test_without_generic_marker_still_falls_back_to_shortest(self):
        """没有通用标记时，仍退回"取最短"——比乱猜好（`鸡蛋` 的真实场景）。

        ⚠️ 这一条是**防止修过头**：新加的通用标记只是"优先"，不该把
           原来的兜底路径整条换掉。

        ⚠️ 顺带钉住"长度相同时顺序稳定"：`鸡蛋(白皮)` 和 `鸡蛋(红皮)`
           都是 6 个字，只按长度排的话结果会随上游返回顺序抖动
           （今天 138、明天 156）。写这个测试时就是这么发现问题的。
        """
        foods = [
            {"name": "鸡蛋(红皮)", "energy_kcal": 156},
            {"name": "鸡蛋(白皮)", "energy_kcal": 138},
        ]
        assert ns._pick_best_food(foods, "鸡蛋")["name"] == "鸡蛋(白皮)"
        # 顺序反过来，结果必须一样
        assert ns._pick_best_food(list(reversed(foods)), "鸡蛋")["name"] == "鸡蛋(白皮)"

    def test_part_words_still_excluded_even_with_marker(self):
        """通用标记不能把"部位词排除"这条规则顶掉（两条是并且的关系）。"""
        foods = [
            {"name": "鸡蛋白(肥,瘦)", "energy_kcal": 60},  # 造一个带标记的部位词
            {"name": "鸡蛋(白皮)", "energy_kcal": 138},
        ]
        assert ns._pick_best_food(foods, "鸡蛋")["name"] == "鸡蛋(白皮)"

    def test_no_match_returns_none(self):
        """完全不像 → 不猜。"""
        foods = [{"name": "白菜", "energy_kcal": 20}]
        assert ns._pick_best_food(foods, "巧克力") is None

    def test_empty_and_missing_energy(self):
        assert ns._pick_best_food([], "豆腐") is None
        # 没有热量的条目要跳过，不能因为它是唯一选项就采用
        assert ns._pick_best_food([{"name": "豆腐"}], "豆腐") is None

    def test_energy_as_string_tolerated(self):
        """上游偶尔把数字给成字符串，要能容忍。"""
        foods = [{"name": "豆腐", "energy_kcal": "81"}]
        assert ns._pick_best_food(foods, "豆腐") is not None


# ============================================================================
# MCP 降级
# ============================================================================


class TestLookupFallback:
    """MCP 不可用时的降级。**核心契约：绝不抛异常，只返回 None。**"""

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self, monkeypatch):
        """开关关掉 → None（业务层据此退化到 AI 估算）。"""
        monkeypatch.setattr(settings, "mcp_enabled", False)
        monkeypatch.setattr(ns, "_cache_get", lambda _name: None)
        assert await ns.lookup_food_nutrition("豆腐") is None

    @pytest.mark.asyncio
    async def test_gateway_failure_returns_none_not_exception(self, monkeypatch):
        """⚠️ 网关返回失败时必须是 None，不能把异常抛给 AI 对话。

        MCP 是"锦上添花"的外部能力——它挂了不该让用户发不出消息。
        """
        monkeypatch.setattr(settings, "mcp_enabled", True)
        monkeypatch.setattr(ns, "_cache_get", lambda _name: None)
        monkeypatch.setattr(ns, "_cache_set", lambda _n, _v: None)

        async def _failing_call(*_args, **_kwargs):
            from app.mcp.gateway import McpResult

            return McpResult(ok=False, error="启动失败: TimeoutError")

        monkeypatch.setattr(ns.gateway, "call_tool", _failing_call)
        assert await ns.lookup_food_nutrition("豆腐") is None

    @pytest.mark.asyncio
    async def test_gateway_raising_returns_none(self, monkeypatch):
        """极端情况：网关自己抛了异常（不该发生，但必须有兜底）。"""
        monkeypatch.setattr(settings, "mcp_enabled", True)
        monkeypatch.setattr(ns, "_cache_get", lambda _name: None)
        monkeypatch.setattr(ns, "_cache_set", lambda _n, _v: None)

        async def _boom(*_args, **_kwargs):
            raise RuntimeError("不该发生的事")

        monkeypatch.setattr(ns.gateway, "call_tool", _boom)
        assert await ns.lookup_food_nutrition("豆腐") is None

    @pytest.mark.asyncio
    async def test_cache_hit_skips_mcp_entirely(self, monkeypatch):
        """⚠️ 缓存命中必须**完全跳过** MCP 调用——不是"结果一样"，是真的没调。

        这是缓存存在的意义：`npx` 起进程的开销（首次要下载包）远大于查询本身。
        """
        monkeypatch.setattr(settings, "mcp_enabled", True)
        cached = ns.FoodNutrition(
            matched_name="豆腐",
            energy_kcal_per_100g=81.0,
            source=ns.SOURCE_MCP_EXACT,
            food_id=1,
        )
        monkeypatch.setattr(ns, "_cache_get", lambda _name: cached)

        called = {"count": 0}

        async def _should_not_be_called(*_args, **_kwargs):
            called["count"] += 1
            raise AssertionError("缓存命中时不该调 MCP")

        monkeypatch.setattr(ns.gateway, "call_tool", _should_not_be_called)

        result = await ns.lookup_food_nutrition("豆腐")
        assert result is cached
        assert called["count"] == 0, "缓存命中却仍然调了 MCP"


# ============================================================================
# 缓存读写
# ============================================================================


class TestCache:
    """缓存层。Redis 不可用时也必须"静默放弃"，不能影响主流程。"""

    def test_key_is_prefixed_and_versioned(self):
        key = ns._cache_key("豆腐")
        assert key.startswith(ns._CACHE_PREFIX)
        assert "豆腐" in key
        # 版本号在 key 里 → 改了**匹配规则**或数据结构时把它 +1，
        # 旧缓存自然失效，不用手动清 Redis。
        #
        # ⚠️ 这里刻意**不写死 v1**：写死的话每次升版本都要改测试，
        #    而"测试因为版本号变了而红"是个假警报，会让人开始无视测试。
        #    只要保证"有个 vN 版本号"这个**性质**就够了。
        assert re.search(r"v\d+", key), "缓存 key 里必须带版本号"

    def test_key_strips_whitespace(self):
        assert ns._cache_key("  豆腐  ") == ns._cache_key("豆腐")

    def test_get_tolerates_redis_unavailable(self, monkeypatch):
        """Redis 挂了 → 返回 None（当作没缓存），不抛异常。"""

        def _no_redis():
            raise ConnectionError("Redis 连不上")

        monkeypatch.setattr(ns, "get_client", _no_redis)
        assert ns._cache_get("豆腐") is None

    def test_set_tolerates_redis_unavailable(self, monkeypatch):
        """Redis 挂了 → 写缓存静默失败，不影响调用方。"""

        def _no_redis():
            raise ConnectionError("Redis 连不上")

        monkeypatch.setattr(ns, "get_client", _no_redis)
        nutrition = ns.FoodNutrition(
            matched_name="豆腐", energy_kcal_per_100g=81.0, source=ns.SOURCE_MCP_EXACT
        )
        ns._cache_set("豆腐", nutrition)  # 不抛就算过

    def test_roundtrip_preserves_source_field(self, monkeypatch):
        """⚠️ `source` 字段必须能存能取——它是"可信度分级"的载体。

        丢了它，接口层就无法区分"查出来的"和"估出来的"，
        面试时说的"用 source 做可信度分级"就落不了地。
        """
        store: dict = {}

        class _FakeRedis:
            def get(self, key):
                return store.get(key)

            def setex(self, key, _ttl, value):
                store[key] = value

        monkeypatch.setattr(ns, "get_client", lambda: _FakeRedis())

        original = ns.FoodNutrition(
            matched_name="排骨(猪)",
            energy_kcal_per_100g=278.0,
            source=ns.SOURCE_MCP_DERIVED,
            food_id=42,
        )
        ns._cache_set("糖醋排骨", original)
        restored = ns._cache_get("糖醋排骨")

        assert restored is not None
        assert restored.source == ns.SOURCE_MCP_DERIVED
        assert restored.matched_name == "排骨(猪)"
        assert restored.energy_kcal_per_100g == 278.0
        assert restored.food_id == 42


# ============================================================================
# 合理性边界
# ============================================================================


class TestSanity:
    """数值合理性。成分表里偶尔有单位标错的条目（比如"每 100g 3000 kcal"）。"""

    def test_reasonable_upper_bound_is_defined(self):
        """上限常量存在且合理——纯油脂约 900 kcal/100g，不能超过 1000。"""
        assert 900 < ns.MAX_REASONABLE_KCAL_PER_100G <= 1000

    def test_to_float_handles_various_inputs(self):
        assert ns._to_float(81) == 81.0
        assert ns._to_float("81.5") == 81.5
        assert ns._to_float(None) is None
        assert ns._to_float("不是数字") is None

    def test_food_nutrition_defaults(self):
        n = ns.FoodNutrition(matched_name="豆腐", energy_kcal_per_100g=81.0, source=ns.SOURCE_MCP_EXACT)
        assert n.food_id is None  # 默认值，调用方可以只给必备字段
