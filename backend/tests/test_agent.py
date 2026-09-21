"""Agent 包（工具层 + ReAct 循环）的测试。

这个包是新加的，而且是**最需要测**的一块：
它把"要执行什么"交给了大模型决定，所以这里是我们**唯一没有完全控制权**的地方。
边界必须靠测试钉住：

  ① **工具不能绕过权限**——工具只是"给模型开的入口"，
     绝不能变成绕开 `ensure_member` 的后门。
  ② **工具失败不能炸掉整轮对话**——用户只是想问个菜，
     不该因为冰箱查询出了点问题就什么都收不到。
  ③ **循环必须有上限**——不设限的话模型可能一直"再查一次"，烧的是真钱。
  ④ **协议消息一条都不能少**——assistant 说要调 N 个工具，
     就必须回 N 条 tool 消息，少一条下一次调用会直接报协议错误。

循环测试用**假的模型调用器**（`_FakeModel`），不打真实 API——
测的是"我们这边怎么处理模型的动作"，跟模型本身聪不聪明无关。
"""

import pytest

from app.agent import react, tools
from app.agent.prompts import SYSTEM_PROMPT, build_system_prompt
from app.agent.tools import ToolContext


def _ctx(space_id: int | None = 1175) -> ToolContext:
    """一个不用连库的上下文。

    只用来测"参数校验 / 分发"这类不碰数据库的路径；
    真正查数据的路径由 tools/check_agent.py 打真库验（单测里不打真库）。
    """
    return ToolContext(session=None, user=None, space_id=space_id)


# ============================================================================
# 工具声明
# ============================================================================


class TestToolSpecs:
    """工具声明是给模型看的契约，形状错了模型就调不动。"""

    def test_five_tools_registered(self):
        assert len(tools.TOOL_SPECS) == 5
        assert set(tools.tool_names()) == {
            "list_fridge_items",
            "get_expiring_items",
            "list_recipes",
            "list_categories",
            "lookup_nutrition",
        }

    def test_every_spec_is_openai_shaped(self):
        for spec in tools.TOOL_SPECS:
            assert spec["type"] == "function"
            function = spec["function"]
            assert function["name"] in tools.tool_names()
            # description 是给模型决定"要不要调"用的，不能是空的
            assert function["description"].strip()
            assert function["parameters"]["type"] == "object"
            assert "properties" in function["parameters"]

    def test_specs_and_handlers_are_in_sync(self):
        """声明的工具和实现的工具必须一一对应。

        ⚠️ 单边漏了会很难查：声明了但没实现 → 模型一调就报"没有这个工具"；
        实现了但没声明 → 那个工具永远不会被调用（像没写一样）。
        """
        declared = {spec["function"]["name"] for spec in tools.TOOL_SPECS}
        assert declared == set(tools.tool_names())

    def test_space_id_is_not_exposed_as_a_parameter(self):
        """⭐ 安全底线：`space_id` 绝不能作为工具参数暴露给模型。

        它是本次对话的上下文，由后端注入（并且已经过 ensure_member）。
        一旦暴露，模型就能自己传一个 ID 进来——那等于给了它一个越权试错的机会。
        """
        for spec in tools.TOOL_SPECS:
            properties = spec["function"]["parameters"]["properties"]
            assert "space_id" not in properties, (
                f"{spec['function']['name']} 把 space_id 暴露成了参数，"
                "这会让模型可以自己指定要查哪个家庭组"
            )

    def test_no_write_tools(self):
        """⭐ 边界：工具清单里**一个写操作都没有**。

        AI 只有"提议权"，写库一律走前端的确认卡片。
        这条边界一旦破了（比如加个 create_recipe 工具），
        模型就有直接改用户数据的能力了——抽错了就是脏数据。
        """
        forbidden = ("create", "update", "delete", "add", "remove", "set", "post")
        for name in tools.tool_names():
            assert not any(word in name for word in forbidden), (
                f"工具 {name} 看起来像写操作。AI 不该有直接改数据的能力。"
            )


# ============================================================================
# 参数解析
# ============================================================================


class TestParseArguments:
    """模型的参数是 JSON **字符串**，而且经常裹 markdown 围栏。"""

    def test_dict_passes_through(self):
        assert tools.parse_arguments({"keyword": "白菜"}) == {"keyword": "白菜"}

    def test_plain_json_string(self):
        assert tools.parse_arguments('{"days": 3}') == {"days": 3}

    def test_markdown_fenced_json(self):
        """模型很爱加 ```json 围栏，不剥掉就解析失败，工具白调一次。"""
        assert tools.parse_arguments('```json\n{"days": 3}\n```') == {"days": 3}

    def test_empty_string_means_no_arguments(self):
        """无参工具（如 list_categories）会给空串，要当空对象。"""
        assert tools.parse_arguments("") == {}
        assert tools.parse_arguments("   ") == {}

    def test_none_means_no_arguments(self):
        assert tools.parse_arguments(None) == {}

    def test_invalid_json_returns_none(self):
        """返回 None 而不是抛错——上层会转成一句"参数不合法"让模型重来。"""
        assert tools.parse_arguments("{不是 json") is None

    def test_json_array_is_rejected(self):
        """合法 JSON 但不是对象 → 也不接受（工具参数必须是对象）。"""
        assert tools.parse_arguments("[1, 2, 3]") is None


# ============================================================================
# 工具执行
# ============================================================================


class TestExecute:
    """执行的错误处理。核心要求：**永远不抛异常**。"""

    async def test_unknown_tool_returns_friendly_error(self):
        result = await tools.execute("不存在的工具", {}, _ctx())
        assert result["ok"] is False
        # 报错里要带上可用清单，模型才知道该怎么改
        assert "list_fridge_items" in result["error"]

    async def test_bad_json_arguments_are_reported(self):
        result = await tools.execute("list_recipes", "{坏的", _ctx())
        assert result["ok"] is False
        assert "JSON" in result["error"]

    async def test_missing_space_id_gives_actionable_message(self):
        """没选家庭组时，要给模型一句**它能转述、也能追问**的话。"""
        result = await tools.execute("list_fridge_items", {}, _ctx(space_id=None))
        assert result["ok"] is False
        assert "家庭组" in result["error"]

    async def test_unexpected_parameter_is_reported(self):
        """模型偶尔会编一个不存在的参数名。要让它知道"只用声明里有的"。"""
        result = await tools.execute("list_fridge_items", {"不存在的参数": 1}, _ctx())
        assert result["ok"] is False
        assert "参数" in result["error"]

    async def test_execute_never_raises(self):
        """⚠️ 这条是整个设计的前提：工具抛异常会毁掉整轮对话。

        用一个必定失败的调用组合验证——不管内部怎么炸，
        对外必须是"返回一个 ok=False 的字典"。
        """
        for name in tools.tool_names():
            result = await tools.execute(name, {"离谱": object()}, _ctx(space_id=None))
            assert isinstance(result, dict)
            assert "ok" in result


# ============================================================================
# ReAct 循环
# ============================================================================


class _FakeModel:
    """假的模型调用器：按剧本返回，并记录每次被调用时的状态。

    为什么不用真模型？——这里要测的是"我们怎么处理模型的动作"，
    跟模型聪不聪明无关。用真模型既慢又贵，还会因为模型偶尔不听话而假失败。
    """

    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)
        self.calls: list[dict] = []

    async def __call__(self, messages: list[dict], tool_specs: list[dict] | None) -> dict:
        self.calls.append({"tool_specs": tool_specs, "message_count": len(messages)})
        if self.script:
            return self.script.pop(0)
        return {"content": '{"intent":"chat","reply":"兜底","actions":[]}', "tool_calls": None}


def _tool_call(name: str, arguments: str = "{}", call_id: str = "call_1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


@pytest.fixture
def fake_tool(monkeypatch):
    """把工具执行换成假的，避免测试里连数据库。

    返回一个可配置的钩子：测试自己决定工具"查到什么"。
    """

    class Hook:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []
            self.result: dict = {"ok": True, "count": 2, "items": [{"name": "白菜"}]}
            self.raises: Exception | None = None

        async def __call__(self, name, raw_arguments, ctx):
            self.calls.append((name, raw_arguments))
            if self.raises is not None:
                raise self.raises
            return self.result

    hook = Hook()
    monkeypatch.setattr(tools, "execute", hook)
    return hook


class TestReactLoop:
    """循环的核心行为。"""

    async def test_direct_answer_needs_one_call(self, fake_tool):
        """模型不需要查数据时，一次调用就结束——别为了"像 Agent"硬凑一轮。"""
        model = _FakeModel([{"content": '{"intent":"chat","reply":"嗯","actions":[]}', "tool_calls": None}])
        messages = [{"role": "user", "content": "今天天气不错"}]

        result = await react.run(messages, _ctx(), model)

        assert len(model.calls) == 1
        assert result.steps == []
        assert result.hit_step_limit is False

    async def test_tool_call_then_answer(self, fake_tool):
        """一轮工具 + 一次回答：这是最常见的路径。"""
        model = _FakeModel(
            [
                {"content": "", "tool_calls": [_tool_call("list_fridge_items", '{"keyword": "白菜"}')]},
                {"content": '{"intent":"chat","reply":"有白菜","actions":[]}', "tool_calls": None},
            ]
        )
        messages = [{"role": "user", "content": "冰箱里有白菜吗"}]

        result = await react.run(messages, _ctx(), model)

        assert len(model.calls) == 2
        assert len(result.steps) == 1
        step = result.steps[0]
        assert step.tool == "list_fridge_items"
        assert step.ok is True
        assert step.arguments == {"keyword": "白菜"}
        assert fake_tool.calls == [("list_fridge_items", '{"keyword": "白菜"}')]

        # 协议：assistant(带 tool_calls) + tool(结果) 两条都要追加进去
        assert [m["role"] for m in messages] == ["user", "assistant", "tool"]
        assert messages[2]["tool_call_id"] == "call_1"
        # 第二轮模型能看到工具结果
        assert model.calls[1]["message_count"] == 3

    async def test_failed_tool_still_appends_tool_message(self, fake_tool):
        """⭐ 工具失败也必须回一条 tool 消息。

        少一条，下一次调用会因为"assistant 说要调工具、却没有结果回来"
        直接报协议错误——一个查询的小毛病升级成整轮对话失败。
        """
        fake_tool.result = {"ok": False, "error": "不是这个家的成员"}
        model = _FakeModel(
            [
                {"content": "", "tool_calls": [_tool_call("list_fridge_items")]},
                {"content": '{"intent":"chat","reply":"查不到","actions":[]}', "tool_calls": None},
            ]
        )
        messages = [{"role": "user", "content": "冰箱有啥"}]

        result = await react.run(messages, _ctx(), model)

        assert result.steps[0].ok is False
        tool_messages = [m for m in messages if m["role"] == "tool"]
        assert len(tool_messages) == 1
        assert "不是这个家的成员" in tool_messages[0]["content"]

    async def test_tool_raising_does_not_break_the_turn(self, fake_tool):
        """⭐ 万一工具真的抛了（比如以后有人改坏了 execute），也不能毁掉整轮对话。"""
        fake_tool.raises = RuntimeError("数据库炸了")
        model = _FakeModel(
            [
                {"content": "", "tool_calls": [_tool_call("list_fridge_items")]},
                {"content": '{"intent":"chat","reply":"没查到","actions":[]}', "tool_calls": None},
            ]
        )
        messages = [{"role": "user", "content": "冰箱有啥"}]

        result = await react.run(messages, _ctx(), model)

        assert result.steps[0].ok is False
        assert len([m for m in messages if m["role"] == "tool"]) == 1

    async def test_multiple_tool_calls_in_one_round(self, fake_tool):
        """一轮里模型可以同时要好几个工具，每个都得有结果回去。"""
        model = _FakeModel(
            [
                {
                    "content": "",
                    "tool_calls": [
                        _tool_call("list_fridge_items", "{}", "call_a"),
                        _tool_call("list_recipes", "{}", "call_b"),
                    ],
                },
                {"content": '{"intent":"recommend","reply":"做白菜","actions":[]}', "tool_calls": None},
            ]
        )
        messages = [{"role": "user", "content": "今天吃啥"}]

        result = await react.run(messages, _ctx(), model)

        assert len(result.steps) == 2
        tool_messages = [m for m in messages if m["role"] == "tool"]
        assert [m["tool_call_id"] for m in tool_messages] == ["call_a", "call_b"]

    async def test_last_call_gets_no_tools(self, fake_tool):
        """⭐ 上限保护：最后一轮**不给工具**，逼它出结果。

        不这么做的话，模型可以无限"再查一次"，每一步都是真金白银。
        """
        # 前三轮都要工具，最后一轮才回答
        script = [
            {"content": "", "tool_calls": [_tool_call("list_fridge_items")]},
            {"content": "", "tool_calls": [_tool_call("list_recipes")]},
            {"content": "", "tool_calls": [_tool_call("list_categories")]},
        ]
        model = _FakeModel(script + [{"content": '{"intent":"chat","reply":"好了","actions":[]}', "tool_calls": None}])
        messages = [{"role": "user", "content": "今天吃啥"}]

        result = await react.run(messages, _ctx(), model)

        # 正常路径总共 4 次调用：3 轮带工具 + 1 次收口
        assert len(model.calls) == react.MAX_STEPS
        assert model.calls[0]["tool_specs"] is not None
        assert model.calls[-1]["tool_specs"] is None, "最后一次调用不该再给工具"
        assert result.hit_step_limit is False
        assert len(result.steps) == 3

    async def test_forced_closure_when_model_ignores_no_tools(self, fake_tool):
        """反常情况：已经不给工具了，模型还是硬要调。

        这时不能继续陪着它绕，只能再要一次回答并如实标记"是被迫收口的"。
        """
        # 每一轮都要工具，包括最后一轮
        script = [{"content": "", "tool_calls": [_tool_call("list_fridge_items")]} for _ in range(6)]
        model = _FakeModel(script)
        messages = [{"role": "user", "content": "今天吃啥"}]

        result = await react.run(messages, _ctx(), model)

        assert result.hit_step_limit is True

    async def test_max_steps_is_configurable(self, fake_tool):
        model = _FakeModel([{"content": '{"intent":"chat","reply":"好","actions":[]}', "tool_calls": None}])
        await react.run([{"role": "user", "content": "嗨"}], _ctx(), model, max_steps=2)
        assert len(model.calls) == 1


class TestSummarize:
    """工具结果 → 一句给人看的过程提示。"""

    def test_lists_show_counts(self):
        assert react._summarize("list_fridge_items", {"ok": True, "count": 4, "items": []}) == "4 条食材"
        assert react._summarize("list_recipes", {"ok": True, "count": 6, "recipes": []}) == "6 道菜"

    def test_truncation_is_visible(self):
        detail = react._summarize(
            "list_recipes", {"ok": True, "count": 80, "recipes": [], "truncated": True}
        )
        assert "已截断" in detail

    def test_nutrition_shows_value(self):
        detail = react._summarize(
            "lookup_nutrition",
            {"ok": True, "found": True, "matched_name": "鸡蛋(白皮)", "energy_kcal_per_100g": 138},
        )
        assert "鸡蛋(白皮)" in detail
        assert "138" in detail

    def test_not_found_is_not_an_error(self):
        """「查了但没有」要说清楚，别让用户以为工具坏了。"""
        assert react._summarize("lookup_nutrition", {"ok": True, "found": False}) == "权威数据源里没有"

    def test_failure_shows_reason(self):
        assert react._summarize("x", {"ok": False, "error": "超时"}) == "超时"


# ============================================================================
# 提示词
# ============================================================================


class TestPrompts:
    def test_date_is_filled_in(self):
        assert "2026-09-21" in build_system_prompt("2026-09-21")

    def test_no_placeholder_left(self):
        """⚠️ `{today}` 必须被填干净——漏了就变成模型看到的一句字面量。

        （这也是为什么这里用 replace 而不是 format：提示词里全是 JSON 花括号。）
        """
        assert "{today}" not in build_system_prompt("2026-09-21")

    def test_forbids_fabricating_household_data(self):
        """最要紧的一条规则必须在提示词里。

        编造冰箱清单比算错热量严重得多——用户可能真的照着去买菜。
        """
        assert "编" in SYSTEM_PROMPT
        assert "必须去查" in SYSTEM_PROMPT

    def test_keeps_json_output_contract(self):
        """输出契约没变（前端还在按它解析），改了要显式发生。"""
        for key in ("intent", "reply", "actions", "food_name", "calories_estimated", "eaten_at"):
            assert key in SYSTEM_PROMPT

    def test_demands_json_after_tool_calls(self):
        """⭐ 实测踩过的坑：模型调完工具就改用大白话回答，不走 JSON 契约了。

        加这条规则前后各跑了一次 check_agent：
        加之前 3/5 个用例降级成了纯文本；加之后 5/5 都按格式输出。
        """
        assert "调用工具之后" in SYSTEM_PROMPT

    def test_tells_model_to_query_main_ingredient(self):
        """⭐ 数据源是《食物成分表》，只有食材没有成品菜。

        不提醒的话它会拿「红烧肉」去查——必然查不到，白白浪费一次查询，
        最后还只能用估算。提醒之后它会直接查「猪肉」。
        """
        assert "主料" in SYSTEM_PROMPT
        assert "猪肉" in SYSTEM_PROMPT

    def test_tool_description_mentions_main_ingredient(self):
        """工具描述里也要说（模型决定"调不调"时看的是 description）。"""
        spec = next(s for s in tools.TOOL_SPECS if s["function"]["name"] == "lookup_nutrition")
        assert "主料" in spec["function"]["description"]
