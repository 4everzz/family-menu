"""MCP 客户端网关测试。

测三件事，对应三种最容易出问题的状态：

  ① **未启用时**：不该产生任何子进程。
     这条最容易被忽略，但它是"默认关闭"这个设计能成立的前提——
     如果关了开关还会偷偷起进程，那默认关闭就只是心理安慰。

  ② **起不来时**：返回 ok=False，而且**不抛异常**。
     MCP Server 是个外部子进程（`npx -y cn-food-mcp`），
     它可能因为没网、npx 不在 PATH、Node 版本不对而启动失败。
     业务代码（nutrition_service）依赖"失败返回 McpResult 而不是抛异常"，
     才能在查不到时优雅降级到 AI 估算。这条契约必须钉死。

  ③ **超时**：到点必须返回，不能把请求永远挂住。

⚠️ 这些测试**不打桩（mock）**，用的是真实行为：
   · 未启用 → 真的读 settings 开关
   · 起不来 → 故意给一个不存在的命令
   · 超时   → 故意给一个永远不说话的"服务端"（sleep）
   为什么不打桩：打桩只能验证"我调的桩被调了"，验证不了真实的进程行为。
   这几个场景恰好都能用真实手段构造，比桩更有说服力，而且更快（不用起 npx）。
"""

import asyncio

import pytest

from app.core.config import settings
from app.mcp import gateway
from app.mcp.servers import McpServerSpec


@pytest.fixture(autouse=True)
def _clean_sessions():
    """每个用例前后清掉会话缓存，避免用例之间互相影响。

    `_sessions` 是模块级字典，一个用例 start 过的会话会留在里面，
    下个用例如果碰巧同名就会拿到上一个用例的残留。
    """
    gateway._reset_sessions_sync()
    yield
    gateway._reset_sessions_sync()


# ============================================================================
# ① 未启用
# ============================================================================


@pytest.mark.asyncio
async def test_disabled_returns_error_without_spawning():
    """关了开关就直接返回失败，不产生任何子进程。"""
    original = settings.mcp_enabled
    settings.mcp_enabled = False
    try:
        result = await gateway.call_tool("food", "search_food", {"query": "豆腐"})
        assert result.ok is False
        assert "未启用" in result.error
        # 关键：没有把会话建起来，也就是没起进程
        assert gateway._sessions == {}
    finally:
        settings.mcp_enabled = original


# ============================================================================
# ② 起不来
# ============================================================================


@pytest.mark.asyncio
async def test_command_not_found_returns_error_not_exception():
    """命令不存在时返回 ok=False，不抛异常。

    用 windows 上肯定不存在的命令名，模拟"npx 没装 / Node 不在 PATH"。
    """
    original_enabled = settings.mcp_enabled
    original_servers = gateway._sessions
    settings.mcp_enabled = True
    gateway._reset_sessions_sync()

    # 临时塞一个必然起不来的 Server 定义
    from app.mcp import servers as servers_module

    broken = McpServerSpec(
        name="broken",
        command="definitely-not-a-real-command-xyz",
        args=[],
        timeout=5.0,
    )
    saved = dict(servers_module._SERVERS)
    servers_module._SERVERS["broken"] = broken
    try:
        result = await gateway.call_tool("broken", "any_tool", {})
        assert result.ok is False
        # 错误信息应该有内容，方便排查（不是空字符串）
        assert result.error
    finally:
        servers_module._SERVERS.clear()
        servers_module._SERVERS.update(saved)
        settings.mcp_enabled = original_enabled
        gateway._reset_sessions_sync()
    _ = original_servers


@pytest.mark.asyncio
async def test_unknown_server_name_returns_error():
    """请求一个没注册过的 Server 名，也要优雅失败。"""
    original = settings.mcp_enabled
    settings.mcp_enabled = True
    gateway._reset_sessions_sync()
    try:
        result = await gateway.call_tool("no-such-server", "some_tool", {})
        assert result.ok is False
        assert result.error
    finally:
        settings.mcp_enabled = original
        gateway._reset_sessions_sync()


# ============================================================================
# ③ 超时
# ============================================================================


@pytest.mark.asyncio
async def test_silent_server_times_out_at_startup():
    """服务端装死时，**起进程阶段就**必须在几秒内失败，不能把请求挂住。

    构造方式：起一个只会 sleep、从不输出 JSON-RPC 的 Python 子进程当"服务端"。
    它永远完不成 initialize 握手，所以调用必然卡在启动阶段。

    ⚠️ 这条用例背后是一个**真实修掉的 bug**，值得记下来：
       最初只给 `session.call_tool` 加了超时，起进程/握手那一段没设。
       结果给 1.5 秒超时，实际跑了 **59.6 秒**——
       因为卡住的是 `session.initialize()`，而清理时的 `stack.aclose()`
       还要等那个睡着的子进程自己结束。
       在真实场景里这表现为"AI 对话页面转圈一分钟"，用户早关了。
       修复：启动整体设 `timeout × 2`，且清理另设 3 秒宽限。
    """
    original_enabled = settings.mcp_enabled
    settings.mcp_enabled = True
    gateway._reset_sessions_sync()

    from app.mcp import servers as servers_module

    # -c 后面这段脚本：什么都不做，只是长时间 sleep，不理会 stdin 上的握手请求。
    # 用 sys.executable 保证命令本身存在（避免又变成"命令找不到"那种失败）。
    import sys

    silent = McpServerSpec(
        name="silent",
        command=sys.executable,
        args=["-c", "import time; time.sleep(60)"],
        timeout=1.5,  # 故意给很短，测试才跑得快
    )
    saved = dict(servers_module._SERVERS)
    servers_module._SERVERS["silent"] = silent
    try:
        started = asyncio.get_running_loop().time()
        result = await asyncio.wait_for(
            gateway.call_tool("silent", "any_tool", {}),
            timeout=30,  # 外层再兜一道，防止网关自身的超时失效导致测试挂死
        )
        elapsed = asyncio.get_running_loop().time() - started

        assert result.ok is False
        # 启动整体超时(timeout×2=3s) + 清理宽限(3s)，留足余量断言 < 12s。
        # 关键是不能接近 60 秒——那说明超时保护完全没生效。
        assert elapsed < 12, f"启动超时保护没生效，耗时 {elapsed:.1f}s"
        assert "失败" in result.error
    finally:
        servers_module._SERVERS.clear()
        servers_module._SERVERS.update(saved)
        settings.mcp_enabled = original_enabled
        gateway._reset_sessions_sync()


# ============================================================================
# 结果解析
# ============================================================================


def test_extract_payload_prefers_structured_content():
    """有 structuredContent 时优先用它。"""
    class _FakeResult:
        structuredContent = {"foods": [{"name": "豆腐"}]}
        content = []

    assert gateway._extract_payload(_FakeResult()) == {"foods": [{"name": "豆腐"}]}


def test_extract_payload_falls_back_to_text_json():
    """没有 structuredContent 时，从首个文本块里解析 JSON。

    cn-food-mcp 走的就是这条路径——它把结果放在 text 里。
    """
    class _Block:
        text = '{"count": 1, "foods": [{"name": "豆腐"}]}'

    class _FakeResult:
        structuredContent = None
        content = [_Block()]

    assert gateway._extract_payload(_FakeResult()) == {
        "count": 1,
        "foods": [{"name": "豆腐"}],
    }


def test_extract_payload_tolerates_garbage():
    """文本不是 JSON 时返回空字典，不抛异常。"""
    class _Block:
        text = "这不是 JSON"

    class _FakeResult:
        structuredContent = None
        content = [_Block()]

    assert gateway._extract_payload(_FakeResult()) == {}
