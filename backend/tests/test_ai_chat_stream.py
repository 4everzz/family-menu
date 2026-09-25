"""流式对话（SSE）的测试。

流式链路比非流式多出三个我们自己写的决策点，都要钉住：

  ① Agent 循环的 `on_step` 回调——每执行完一个工具必须回调一次，
     一步都不能少（少一步前端就少亮一行"它查了什么"）。
  ② `chat_stream` 的事件序列——start → step* → message → done；
     业务失败时必须是 error 事件且**没有** message（前端据此区分成功失败）。
  ③ SSE 帧的编码——帧边界是空行，data 里的换行必须被 json 转义，
     否则会把帧切碎、前端解析直接乱套。

不打真实模型：`_call_model` 全部用假件替换（与 test_ai_chat_service.py 同一思路）。
"""

import pytest

from app.agent import react
from app.agent.tools import ToolContext
from app.api.v1.ai_chat import _sse
from app.core.config import settings
from app.core.response import CODE_PARAM_INVALID
from app.models.user import User
from app.schemas.ai_chat import AiChatRequest
from app.services import ai_quota_service
from app.services.ai_chat_service import AiChatService


class TestReactOnStep:
    """Agent 循环的步骤回调：流式通道的数据源。"""

    async def test_callback_receives_every_step(self):
        """调了一个工具 → 回调必须恰好收到一步。"""
        calls = [
            {
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {"name": "list_fridge_items", "arguments": "{}"},
                    }
                ]
            },
            {"content": '{"intent":"chat","reply":"好","actions":[]}'},
        ]

        async def fake_model(messages, tools_):
            return calls.pop(0)

        seen: list[str] = []

        async def on_step(step):
            seen.append(step.tool)

        # session/user 传 None：这一步的工具执行会失败（被 execute 兜成 ok=False），
        # 但"失败也是一步"——回调照样要收到，前端才能把"查冰箱失败了"亮出来
        ctx = ToolContext(session=None, user=None, space_id=None)
        result = await react.run(
            [{"role": "user", "content": "有什么"}],
            ctx,
            fake_model,
            on_step=on_step,
        )

        assert seen == ["list_fridge_items"]
        assert len(result.steps) == 1

    async def test_no_callback_changes_nothing(self):
        """不传 on_step：行为与非流式完全一致（回调是纯增量，不许有副作用）。"""
        calls = [{"content": '{"intent":"chat","reply":"好","actions":[]}'}]

        async def fake_model(messages, tools_):
            return calls.pop(0)

        ctx = ToolContext(session=None, user=None, space_id=None)
        result = await react.run([{"role": "user", "content": "在吗"}], ctx, fake_model)

        assert result.steps == []
        assert "好" in result.content


class _FakeRepo:
    """够 chat() 跑通的假仓储：不碰库。"""

    async def list_recent(self, user_id, limit, space_id=None):
        return []

    async def add_user_message(self, *args, **kwargs):
        pass

    async def add_assistant_message(self, *args, **kwargs):
        pass


class TestChatStream:
    """chat_stream 的事件序列。"""

    @staticmethod
    def _service_with(fake_call) -> AiChatService:
        service = AiChatService(repo=_FakeRepo(), session=None)

        async def _fake(messages, tools_):
            return await fake_call(messages, tools_)

        service._call_model = _fake  # type: ignore[method-assign]
        return service

    @staticmethod
    def _patch_env(monkeypatch):
        """不碰真额度、不依赖 .env 里有没有配 Key。"""
        monkeypatch.setattr(ai_quota_service, "consume", lambda user_id: None)
        monkeypatch.setattr(
            type(settings),
            "chat_api_key_effective",
            property(lambda self: "test-key"),
        )

    async def test_event_sequence_with_tool_step(self, monkeypatch):
        """调了一次工具的正常轮次：start → step → message → done，一步不缺。"""
        self._patch_env(monkeypatch)

        calls = [
            {
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {"name": "list_fridge_items", "arguments": "{}"},
                    }
                ]
            },
            {"content": '{"intent":"chat","reply":"冰箱里有鸡蛋","actions":[]}'},
        ]

        async def fake_call(messages, tools_):
            return calls.pop(0)

        service = self._service_with(fake_call)
        user = User(id=1, username="tester")
        payload = AiChatRequest(message="我冰箱里还有什么")

        events = [event async for event in service.chat_stream(user, payload)]
        names = [name for name, _ in events]
        assert names == ["start", "step", "message", "done"]

        # step 事件的形状要和 AgentStepInfo 对齐（前端靠它复用同一套渲染）
        assert events[1][0] == "step"
        assert events[1][1]["tool"] == "list_fridge_items"
        assert "ok" in events[1][1]
        assert "detail" in events[1][1]

        # message 事件的 data 必须与 /ai/chat 的返回结构一致——
        # 这是"前端渲染逻辑零改动"这条承诺的落点
        assert events[2][0] == "message"
        assert events[2][1]["reply"] == "冰箱里有鸡蛋"
        assert events[2][1]["steps"][0]["tool"] == "list_fridge_items"

    async def test_chat_without_tools_has_no_step_event(self, monkeypatch):
        """闲聊（一次工具都没调）：start 直接到 message，中间不许有空 step。"""
        self._patch_env(monkeypatch)

        async def fake_call(messages, tools_):
            return {"content": '{"intent":"chat","reply":"你好呀","actions":[]}'}

        service = self._service_with(fake_call)
        payload = AiChatRequest(message="你好")

        events = [event async for event in service.chat_stream(User(id=1, username="t"), payload)]
        assert [name for name, _ in events] == ["start", "message", "done"]

    async def test_business_error_becomes_error_event(self):
        """业务失败（这里是空消息）→ error 事件，且**没有** message/done。

        ⚠️ 流式响应的 HTTP 头早已按 200 发出，前端只能靠 error 事件知道失败了。
        """
        service = AiChatService(repo=_FakeRepo(), session=None)
        payload = AiChatRequest(message="   ")  # 空消息 → BusinessError

        events = [event async for event in service.chat_stream(User(id=1, username="t"), payload)]
        names = [name for name, _ in events]
        assert names == ["start", "error"]
        assert events[1][1]["code"] == CODE_PARAM_INVALID
        assert events[1][1]["message"]


class TestSseFrame:
    """SSE 帧编码：帧边界是空行，这是前端切帧的唯一依据。"""

    def test_frame_format(self):
        frame = _sse("step", {"tool": "list_fridge_items"})
        assert frame == 'event: step\ndata: {"tool": "list_fridge_items"}\n\n'

    def test_newline_inside_json_is_escaped(self):
        """data 里的换行必须被 json 转义成 \\n——
        真实换行会把一帧切成两帧，前端解析直接乱套。"""
        frame = _sse("message", {"reply": "第一行\n第二行"})
        assert frame.count("\n\n") == 1
        assert 'data: {"reply": "第一行\\n第二行"}' in frame

    def test_chinese_stays_readable(self):
        """ensure_ascii=False：中文原样输出，别把带宽浪费在 \\uXXXX 上。"""
        frame = _sse("message", {"reply": "冰箱里有鸡蛋"})
        assert "冰箱里有鸡蛋" in frame
