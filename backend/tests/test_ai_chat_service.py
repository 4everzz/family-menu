"""AI 对话服务里「我们自己写的决策点」的测试。

`chat()` 本身要调外部大模型（没 Key 走不通、有 Key 也不该在单测里烧钱），
所以这里只测**不依赖模型**的那几块——它们恰好也是最容易出错、
出错了后果最严重的地方：

  ① 营养来源分级（`_parse_actions` 判 source）——决定"标成查到的还是估的"。
     这个字段要写进接口返回、给前端显示可信度，也是简历里
     "可信度分级"那句话的落点。判错等于**用一个精确的外观包装一个不准的数字**，
     比直接给个模糊估计更糟——用户会当真。

  ② 从实际执行过的工具里还原营养数据（`_nutrition_from_steps`）。
     ⭐ 这是改造后新增的一环：source 必须由"工具确实被调过、确实查到了"
     这个**事实**决定，而不是模型自己在 JSON 里报一个它想报的值。

  ③ 模型输出的解析与降级（`_parse`）。

⚠️ 改造后 `_extract_dish_name`（那套抠菜名的正则）整块删掉了——
   "调不调工具"现在由模型自己判断，不再靠正则硬凑。
   原来那 11 个正则用例随之作废，换成下面这些。
"""

from app.agent.prompts import REFORMAT_INSTRUCTION
from app.agent.react import AgentStep
from app.core.exceptions import BusinessError
from app.services import nutrition_service as ns
from app.services.ai_chat_service import AiChatService, _nutrition_from_steps
# `_parse` / `_parse_actions` 都不碰 repo 和 session，传 None 就够。
# （这样能测到真实的方法，而不用为了"能构造"去写一堆假对象。）
_service = AiChatService(repo=None, session=None)


def _step(
    tool: str = "lookup_nutrition",
    ok: bool = True,
    data: dict | None = None,
) -> AgentStep:
    """造一步工具调用记录。"""
    return AgentStep(
        tool=tool,
        arguments={},
        ok=ok,
        detail="",
        data=data if data is not None else {},
    )


class TestNutritionFromSteps:
    """从工具执行记录里还原营养数据（source 标注的事实依据）。"""

    def test_found_true_yields_nutrition(self):
        steps = [
            _step(data={"ok": True, "found": True, "matched_name": "鸡蛋(白皮)", "energy_kcal_per_100g": 138})
        ]
        result = _nutrition_from_steps(steps)
        assert result is not None
        assert result.matched_name == "鸡蛋(白皮)"
        assert result.energy_kcal_per_100g == 138.0

    def test_found_false_yields_none(self):
        """查了但没有 —— 必须回 None，让上层标成估算。

        ⚠️ 这条最容易写错：把"工具调成功了"当成"查到了数据"，
           结果给用户标一个"已核对"的标签，实际数字是模型编的。
        """
        steps = [_step(data={"ok": True, "found": False})]
        assert _nutrition_from_steps(steps) is None

    def test_failed_step_yields_none(self):
        """工具失败了 → 不算查到（不能拿失败的结果当依据）。"""
        steps = [_step(ok=False, data={"ok": False, "error": "超时"})]
        assert _nutrition_from_steps(steps) is None

    def test_no_lookup_step_yields_none(self):
        """这轮压根没查热量（比如用户只是闲聊）→ 估算。"""
        steps = [_step(tool="list_fridge_items", data={"ok": True, "items": []})]
        assert _nutrition_from_steps(steps) is None

    def test_empty_steps_yields_none(self):
        assert _nutrition_from_steps([]) is None

    def test_energy_not_a_number_yields_none(self):
        """上游给了个没法用的值 → 当作没查到，别让它污染标注。"""
        steps = [_step(data={"ok": True, "found": True, "matched_name": "豆腐", "energy_kcal_per_100g": "很多"})]
        assert _nutrition_from_steps(steps) is None


class TestSourceLabeling:
    """营养来源分级。

    为什么这个测试重要：
      接口返回里的 `source` 字段决定了前端怎么展示——是"已核对"还是"AI 估算"。
      把估算标成查到的，用户会当真；这比"估得不准"严重得多。
      这三级的值定义在 nutrition_service 里，接口层直接引用，不能各写各的字符串。
    """

    def test_three_levels_are_distinct(self):
        levels = {
            ns.SOURCE_MCP_EXACT,
            ns.SOURCE_MCP_DERIVED,
            ns.SOURCE_LLM_ESTIMATE,
        }
        assert len(levels) == 3, "三个来源等级必须互不相同"

    def test_level_values_are_stable_strings(self):
        """这三个值会写进接口响应、可能被前端/DB 依赖，改动要**显式**发生。

        钉住字面量，是为了将来重构时不声不响地改名——
        改名会让历史数据里的旧值变成"未知来源"，前端渲染就崩了。
        """
        assert ns.SOURCE_MCP_EXACT == "mcp_exact"
        assert ns.SOURCE_MCP_DERIVED == "mcp_derived"
        assert ns.SOURCE_LLM_ESTIMATE == "llm_estimate"


class TestParseActions:
    """动作草案的校验与来源标注。"""

    _RAW = [
        {
            "kind": "create_calorie_log",
            "food_name": "红烧肉",
            "portion": "500g",
            "calories": 550,
            "calories_estimated": False,
            "eaten_at": "2026-09-21",
        }
    ]

    @staticmethod
    def _nutrition() -> ns.FoodNutrition:
        return ns.FoodNutrition(
            matched_name="猪肉",
            energy_kcal_per_100g=395.0,
            source=ns.SOURCE_MCP_EXACT,
        )

    def test_no_nutrition_marks_estimate(self):
        """这轮没查到权威数据 → 一律标成估算。"""
        actions = AiChatService._parse_actions(self._RAW, None)
        assert len(actions) == 1
        assert actions[0].source == ns.SOURCE_LLM_ESTIMATE
        assert actions[0].matched_food is None

    def test_nutrition_plus_not_estimated_marks_exact(self):
        """查到了、且模型说"不是估的" → 它直接用了查到的值。"""
        actions = AiChatService._parse_actions(self._RAW, self._nutrition())
        assert actions[0].source == ns.SOURCE_MCP_EXACT
        assert actions[0].matched_food == "猪肉"

    def test_nutrition_plus_estimated_marks_derived(self):
        """查到了、但模型说是估的 → 它对基准值做了烹饪修正。"""
        raw = [{**self._RAW[0], "calories_estimated": True}]
        actions = AiChatService._parse_actions(raw, self._nutrition())
        assert actions[0].source == ns.SOURCE_MCP_DERIVED
        assert actions[0].matched_food == "猪肉"

    def test_out_of_range_calories_are_dropped(self):
        """热量离谱（听错/多打个 0）→ 置空并标成估算，留给用户自己填。

        ⚠️ 不采信但**也不丢整条**：菜名是对的，卡片让用户补个数字比什么都不给好。
        """
        raw = [{**self._RAW[0], "calories": 999999}]
        actions = AiChatService._parse_actions(raw, None)
        assert actions[0].calories is None
        assert actions[0].calories_estimated is True

    def test_action_without_food_name_is_dropped(self):
        raw = [{**self._RAW[0], "food_name": "   "}]
        assert AiChatService._parse_actions(raw, None) == []

    def test_unknown_kind_is_dropped(self):
        """不认识的动作品种一律丢掉——只认自己实现过的那一种。"""
        raw = [{**self._RAW[0], "kind": "delete_everything"}]
        assert AiChatService._parse_actions(raw, None) == []

    def test_non_list_input_is_safe(self):
        assert AiChatService._parse_actions("不是列表", None) == []


class TestParse:
    """模型输出 → 结构化响应。"""

    def test_valid_json_is_parsed(self):
        content = (
            '{"intent":"log","reply":"记下了","actions":['
            '{"kind":"create_calorie_log","food_name":"苹果","calories":90,'
            '"calories_estimated":true,"eaten_at":"2026-09-21"}]}'
        )
        result = _service._parse(content, None, [])
        assert result.intent == "log"
        assert result.reply == "记下了"
        assert len(result.actions) == 1

    def test_recommend_is_no_longer_degraded(self):
        """⭐ 改造后 recommend 是**真能用**的（模型能查冰箱和菜单再推荐）。

        改造前"推荐"在提示词里被明确写成"我还在学"，所以那时把 recommend
        降级成 chat 也无所谓；现在降级反而会把一个正常结果吃掉。
        """
        result = _service._parse('{"intent":"recommend","reply":"做大虾吧","actions":[]}', None, [])
        assert result.intent == "recommend"

    def test_log_without_actions_degrades_to_chat(self):
        """说是记账却没抽出动作 → 降级成 chat，否则前端渲染一张空卡片。"""
        result = _service._parse('{"intent":"log","reply":"好的","actions":[]}', None, [])
        assert result.intent == "chat"

    def test_unknown_intent_falls_back_to_chat(self):
        result = _service._parse('{"intent":"乱写的","reply":"嗯","actions":[]}', None, [])
        assert result.intent == "chat"

    def test_broken_json_falls_back_to_raw_text(self):
        """⚠️ 解析失败**不抛错**：把模型原文当回复。

        用户的话已经在模型那儿走了一圈，直接报错等于把这次交互整个丢掉；
        显示原文至少让人看到"它在说什么"，也方便我们发现是提示词的问题。
        """
        result = _service._parse("模型今天没按格式说话", None, [])
        assert result.reply == "模型今天没按格式说话"
        assert result.intent == "chat"
        assert result.actions == []

    def test_steps_are_attached_to_response(self):
        """工具调用过程要带出去——前端靠它显示"它真的去查了"。"""
        steps = [_step(tool="list_fridge_items", data={"ok": True, "count": 4, "items": []})]
        result = _service._parse('{"intent":"chat","reply":"有 4 样","actions":[]}', None, steps)
        assert len(result.steps) == 1
        assert result.steps[0].tool == "list_fridge_items"
        assert result.steps[0].ok is True

    def test_steps_survive_broken_json(self):
        """降级成纯文本时也要带 steps：用户至少知道"它查了但没吐出结构化结果"。"""
        steps = [_step(tool="list_fridge_items", data={"ok": True, "count": 4, "items": []})]
        result = _service._parse("没按格式说话", None, steps)
        assert len(result.steps) == 1


class TestEnsureJson:
    """输出契约的兜底：模型漂了就再问它一次。

    ⭐ 为什么这块必须有测试？
       它守的是"记一笔热量"这个核心功能的**静默失效**——
       模型用大白话回答时，用户看到的回复很正常，但确认卡片永远不会出现。
       这种故障没有任何报错，只能靠这层补救 + 测试盯住。
    """

    @staticmethod
    def _service_with(fake_call):
        """造一个 _call_model 被换掉的服务实例（不碰真 API）。"""
        service = AiChatService(repo=None, session=None)

        async def _fake(messages, tools):
            return await fake_call(messages, tools)

        service._call_model = _fake  # type: ignore[method-assign]
        return service

    async def test_valid_json_costs_no_extra_call(self):
        """已经是 JSON 就**一次额外调用都不能有**——不能让兜底变成常态开销。"""
        calls: list = []

        async def fake_call(messages, tools):
            calls.append(tools)
            return {"content": "不该被调用"}

        service = self._service_with(fake_call)
        out = await service._ensure_json('{"intent":"chat","reply":"好","actions":[]}', [])
        assert calls == []
        assert out.startswith("{")

    async def test_plain_text_triggers_one_reformat(self):
        seen: dict = {}

        async def fake_call(messages, tools):
            seen["tools"] = tools
            seen["last"] = messages[-1]["content"]
            seen["has_original"] = any(
                m.get("content") == "白菜还有 1 颗" for m in messages
            )
            return {"content": '{"intent":"chat","reply":"白菜还有 1 颗","actions":[]}'}

        service = self._service_with(fake_call)
        out = await service._ensure_json("白菜还有 1 颗", [{"role": "user", "content": "有白菜吗"}])

        assert "白菜还有 1 颗" in out
        assert seen["last"] == REFORMAT_INSTRUCTION
        # 重排版请求要带上原文，否则等于让它凭空再答一次
        assert seen["has_original"] is True
        # 重排版时不给工具：这次只是"换个格式说"，不该再去查一遍
        assert seen["tools"] is None

    async def test_reformat_still_broken_keeps_original(self):
        """补一次还是大白话 → 沿用原文，别把这次交互整个丢掉。"""

        async def fake_call(messages, tools):
            return {"content": "还是大白话"}

        service = self._service_with(fake_call)
        assert await service._ensure_json("大白话", []) == "大白话"

    async def test_reformat_http_error_keeps_original(self):
        """补救调用自己失败了（网络抖、限流）→ 同样沿用原文。"""

        async def fake_call(messages, tools):
            raise BusinessError("AI 服务暂时不可用，请稍后重试")

        service = self._service_with(fake_call)
        assert await service._ensure_json("大白话", []) == "大白话"
