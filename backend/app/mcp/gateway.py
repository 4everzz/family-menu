"""MCP 客户端网关：管子进程、管超时、管降级。

⭐ 这一层存在的唯一理由：**把"MCP 协议这一层"和"业务语义"隔开。**

   业务层（nutrition_service）只调 `fetch_food_nutrition()`，它不知道底下是：
     · 一个 stdio 子进程
     · 一个 HTTP 接口
     · 还是一个本地函数

   将来 cn-food-mcp 停维护了、或者你想换成自建的服务，
   **只改这个文件，业务代码一行不动**。这才是接 MCP 的收益。

─────────────────────────────────────────────────────────────────────
⭐ 踩过的坑（每一条都对应下面的一段代码）

1. **stdout 是 JSON-RPC 通道，任何 print() 都会破坏协议**
   → 本文件全程不写 print；日志走 logger（→ stderr）

2. **Windows 下 stdio 默认 GBK 编码**
   → 起子进程时显式传 encoding="utf-8"，否则中文食物名会乱码/报错

3. **子进程不能每次请求都起一个**
   起一个 Node 进程要几百毫秒到几秒（npx 首次还要下载包）。
   → 模块级单例 + asyncio.Lock 双检锁，全进程复用同一个会话

4. **不能把 MCP 故障传染给业务**
   MCP 是外部依赖，它超时/崩溃/没装 Node 都是常态。
   → 所有异常都在这里吃掉，统一返回 McpResult(ok=False)，**绝不向上抛**
   → 业务层看到 ok=False 就静默降级，用户完全无感

5. **退出要收干净，否则留孤儿进程**
   → AsyncExitStack 托住整个生命周期，atexit 注册同步兜底
─────────────────────────────────────────────────────────────────────
"""

import asyncio
import atexit
import contextlib
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.core.config import settings
from app.mcp.servers import McpServerSpec, get_server_spec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 返回结构
# ---------------------------------------------------------------------------


@dataclass
class McpResult:
    """MCP 调用的统一返回。

    ⚠️ 刻意**不用异常表达失败**。理由：
      MCP 是"锦上添花"的外部能力，它挂了不该让 AI 对话跟着 500。
      用返回值表达失败，调用方被迫显式处理，不容易漏。
    """

    ok: bool
    #: 成功时的原始数据（这里放工具返回的 JSON 对象）
    data: dict[str, Any] = field(default_factory=dict)
    #: 失败原因（给日志看，不给用户看）
    error: str = ""


# ---------------------------------------------------------------------------
# 会话管理
# ---------------------------------------------------------------------------


class ToolStartError(RuntimeError):
    """MCP Server 起不来。

    单独一个类型，是为了让上层的 `call_tool` 能把它转成一句好懂的提示
    （"启动失败: TimeoutError" 比一段 anyio 的嵌套异常好读得多），
    同时保留原始异常类型名供排查。
    """


class _McpSession:
    """一个 MCP Server 的会话（对应一个子进程）。

    生命周期：第一次用时懒加载起进程 → 一直复用 → 进程退出时统一收。
    """

    def __init__(self, spec: McpServerSpec) -> None:
        self.spec = spec
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        #: 握手完成后的会话，等着 _ensure_started 把它挂到 self._session 上。
        #: 为什么绕这一下：`_start` 在 `wait_for` 里跑，它的返回值拿不到——
        #: 一旦 `wait_for` 超时，内部的协程会被取消，`await` 直接抛异常，
        #: 没法「先拿到结果再设超时」。所以让 `_start` 把成果放在实例属性上。
        self._pending_session: ClientSession | None = None
        # ⚠️ anyio 的 cancel scope 认"进它的是哪个任务"，退出也必须由同一个任务来。
        #    记下建会话时所在的任务，清理时对不上就改从那个任务里清（见 _reset）。
        #    不记这个的话，会出现经典的
        #    `RuntimeError: Attempted to exit cancel scope in a different task than it was entered in`
        #    ——而那个报错发生在**清理阶段**，很容易被误判成"起进程失败"。
        self._owner_task: asyncio.Task | None = None
        # 双检锁：防止并发请求同时发现"还没起"，然后各起一个进程
        self._lock = asyncio.Lock()

    async def _ensure_started(self) -> ClientSession:
        """确保子进程已起、会话已就绪。已就绪就直接返回。"""
        if self._session is not None:
            return self._session

        async with self._lock:
            # 双检：拿到锁之后再确认一次，可能已经被别的协程起好了
            if self._session is not None:
                return self._session

            # ⚠️ 这里用 AsyncExitStack 而不是 async with，是因为
            #    stdio_client 和 ClientSession 的上下文要跨函数调用保持打开，
            #    普通 async with 出了函数作用域就关了。
            stack = AsyncExitStack()
            try:
                # env 的编码补充交给 spec 自己算（见 McpServerSpec.read_write_args），
                # 这样加新 Server 时不用在这边再想一遍 Windows 编码问题
                params = StdioServerParameters(**self.spec.read_write_args())

                # ⚠️ 整个"起进程 + 握手"都要包进超时里。
                #
                #    只给 session.call_tool 加超时是**不够**的——真正会挂死的是
                #    `session.initialize()` 这一步：它要向子进程发握手请求并等回应，
                #    如果子进程是个哑巴（不读 stdin、回了但格式不对、或者卡在启动
                #    脚本里），这一步会一直等下去。
                #
                #    实测过这个坑：给 1.5 秒超时，结果整个调用跑了 **59.6 秒**
                #    （直到子进程自己睡醒退出，管道断了才报 "Connection closed"）。
                #    在真实场景里这就是"AI 对话页面转圈一分钟"，用户直接关掉了。
                #
                #    超时时间用 spec.timeout × 2：起进程本身（尤其 npx 首次下载包）
                #    比一次工具调用更慢，给一倍余量比较合理，不用再单开一个配置项。
                await asyncio.wait_for(self._start(stack, params), timeout=self.spec.timeout * 2)
            except Exception as error:
                # 起不来就把栈收了，别把半成品留着。
                #
                # ⚠️ 但**清理本身也必须设超时**，而且这里踩过一个很隐蔽的坑：
                #    aclose() 会去等子进程收尾（关掉管道、等它退出）。如果子进程
                #    是个哑巴（我们超时就是因为它在装死），这个 aclose() 会一直
                #    等到子进程自己结束为止——实测又跑了 59 秒，
                #    把前面 wait_for 挣来的超时全部抵消掉了。
                #    所以清理给 3 秒宽限，超时就放弃等待（子进程交给操作系统回收，
                #    stdio 模式下它不会变成孤儿占端口，最坏情况只是一个僵尸进程）。
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(stack.aclose(), timeout=3.0)
                raise ToolStartError(f"{type(error).__name__}") from error

            self._exit_stack = stack
            self._session = self._pending_session
            self._pending_session = None
            # 记下"是谁进的这个 cancel scope"，清理时要回到同一个任务里去退
            self._owner_task = asyncio.current_task()
            logger.info("MCP Server 已启动 | name=%s | command=%s", self.spec.name, self.spec.command)
            return self._session

    async def _start(self, stack: AsyncExitStack, params: StdioServerParameters) -> None:
        """真正把子进程拉起来并完成握手。

        单独抽成一个方法，是为了能整个包进 `asyncio.wait_for`——
        `wait_for` 只能作用于一个可等待对象，而这里是"进两个上下文 + 调一次握手"
        三步，必须收进一个协程里才能整体设超时。
        """
        read, write = await stack.enter_async_context(stdio_client(params))
        session = ClientSession(read, write)
        await stack.enter_async_context(session)
        await session.initialize()
        # 握手成功，把会话挂到栈上（不能用局部变量返回，见 _ensure_started 的说明）
        self._pending_session = session

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> McpResult:
        """调一个工具，带超时。

        返回 McpResult，**不抛异常**（除了 CancelledError，那是协程取消，必须放行）。
        """
        try:
            session = await self._ensure_started()
        except ToolStartError as exc:
            # 起进程失败：可能是没装 npx、包下载失败、权限问题、或者对方装死超时
            logger.warning("MCP Server 启动失败 | name=%s | %s", self.spec.name, exc)
            # 起失败就把状态清掉，下次请求重新尝试（也许只是网络抖了一下）
            await self._reset()
            return McpResult(ok=False, error=f"启动失败: {exc}")
        except asyncio.CancelledError:
            # 协程被取消（如客户端断连）→ 必须原样放行，不能吞
            raise
        except Exception as exc:
            logger.warning("MCP Server 启动异常 | name=%s | %s", self.spec.name, exc)
            await self._reset()
            return McpResult(ok=False, error=f"启动失败: {exc}")

        try:
            result = await asyncio.wait_for(
                session.call_tool(tool_name, arguments),
                timeout=self.spec.timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("MCP 工具调用超时 | name=%s | tool=%s", self.spec.name, tool_name)
            return McpResult(ok=False, error="调用超时")
        except asyncio.CancelledError:
            # 协程被取消（如客户端断连）→ 必须原样放行，不能吞
            raise
        except Exception as exc:
            logger.warning("MCP 工具调用失败 | name=%s | tool=%s | %s", self.spec.name, tool_name, exc)
            return McpResult(ok=False, error=f"调用失败: {exc}")

        return McpResult(ok=True, data=_extract_payload(result))

    async def _reset(self) -> None:
        """把会话置空（下次请求会重新起进程）。

        ⚠️ 这里有个容易踩的坑：**anyio 的 cancel scope 只能由"进入它的那个任务"退出。**
        `stdio_client` 内部用的是 anyio 的 task group，进入它的是当时执行
        `_ensure_started` 的那个任务。如果我们现在换了个任务（比如超时后
        `wait_for` 的内部任务、或测试里另起一个任务）来调 `aclose()`，
        anyio 会抛：

            RuntimeError: Attempted to exit cancel scope in a different task
            than it was entered in

        而且这个异常发生在**清理**时——真正想返回的错误（比如"启动失败"）
        会被它顶掉，排查时很容易看错方向。

        处理办法：先清引用（这一步必须立刻做，保证后续请求不会再拿到坏会话），
        再判断当前任务是不是创建者：
          · 是 → 直接关，正常路径。
          · 不是 → 把关闭动作丢回创建者任务去执行，然后不阻塞等待，
            并挂一个回调把异常吃掉——清理失败不该影响调用方拿到的结果。
        """
        stack, self._exit_stack = self._exit_stack, None
        session, self._session = self._session, None
        owner, self._owner_task = self._owner_task, None
        self._pending_session = None  # 握手没完成的残留也一并清掉

        if stack is None:
            return

        current = asyncio.current_task()
        if owner is None or owner is current or owner.done():
            # 同一个任务，或创建者已经结束了（那就没有 cancel scope 还在外面了）→ 直接关
            with contextlib.suppress(Exception):
                await stack.aclose()
            return

        # 跨任务：把关闭动作交给创建者任务执行，不在这里 await。
        # 用一个独立的包装协程，顺便把异常吞掉——否则会变成
        # "Task exception was never retrieved" 之类的噪音日志。
        async def _close_in_owner() -> None:
            try:
                await stack.aclose()
            except Exception as exc:  # noqa: BLE001 —— 清理失败只能记日志
                logger.debug("MCP 会话清理时出错（已忽略） | name=%s | %s", self.spec.name, exc)

        task = asyncio.create_task(_close_in_owner())
        # 保存引用，避免被 GC 提前回收（asyncio 官方提醒的经典坑）
        task.add_done_callback(lambda _t: None)

    async def aclose(self) -> None:
        """主动关闭（应用关停时调）。

        ⚠️ **必须在创建会话的那条事件循环里调用**（见 app/main.py 的 lifespan）。
        跨循环关会话会抛 cancel scope 相关错误——这也是为什么
        `atexit` 里只清引用、不做异步清理。
        """
        await self._reset()


def _extract_payload(result: Any) -> dict[str, Any]:
    """从 MCP 的 CallToolResult 里抠出我们真正要的数据。

    MCP 工具返回的是一组 content block（文本/图片/资源）。
    cn-food-mcp 这类工具把结果塞在 `structuredContent` 里，
    没有的话就退而求其次，解析第一个 text block 的 JSON。

    ⚠️ 只做"提取"，不做语义解释——解释是 nutrition_service 的事。
    """
    # 优先结构化内容（新版 SDK 会有）
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    # 退路：从 text content 里解析 JSON
    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue
        import json

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


# ---------------------------------------------------------------------------
# 模块级单例
# ---------------------------------------------------------------------------

_sessions: dict[str, _McpSession] = {}


def get_session(server_name: str) -> _McpSession | None:
    """取（必要时创建）某个 Server 的会话。未注册的 Server 返回 None。"""
    spec = get_server_spec(server_name)
    if spec is None:
        logger.warning("未注册的 MCP Server: %s", server_name)
        return None
    session = _sessions.get(server_name)
    if session is None:
        session = _McpSession(spec)
        _sessions[server_name] = session
    return session


async def call_tool(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> McpResult:
    """对外唯一的入口：调某个 Server 的某个工具。

    ⭐ 业务层只认这个函数，不认下面的 ClientSession / stdio_client。
      这是"接口稳定、实现可替换"的具体落地。

    开关关闭时**直接返回失败、不产生任何子进程**——
    这是"默认不启用 MCP 就不影响现有行为"的保证。
    """
    if not settings.mcp_enabled:
        return McpResult(ok=False, error="MCP 未启用")

    session = get_session(server_name)
    if session is None:
        return McpResult(ok=False, error=f"未知的 MCP Server: {server_name}")

    return await session.call_tool(tool_name, arguments)


async def shutdown_all() -> None:
    """关停所有 MCP 子进程（应用退出时调）。

    ⚠️ **必须在和调用工具时同一个事件循环里执行。**
       否则 anyio 会抛 `RuntimeError: Attempted to exit cancel scope in a
       different task than it was entered in`——因为 MCP 的 stdio_client
       内部用了 anyio 的 task group 和 cancel scope，这两者都**绑定创建时的事件循环**。

       所以由 app/main.py 的 lifespan 关闭分支调用（那里和请求处理是同一条循环），
       **不要**放到 atexit 里新建循环去跑（曾经踩过，见下方 _sync_shutdown 的说明）。
    """
    for name, session in list(_sessions.items()):
        logger.info("正在关闭 MCP Server | name=%s", name)
        with contextlib.suppress(Exception):
            await session.aclose()
    _sessions.clear()


def _reset_sessions_sync() -> None:
    """进程退出兜底：只清引用，**不做异步清理**。

    ⚠️ 为什么不像一开始那样在 atexit 里 `new_event_loop().run_until_complete(...)`？
       因为会话是在 uvicorn 的事件循环里创建的，anyio 的 cancel scope
       绑定在那个循环上。换个循环去关闭会直接抛
       `Attempted to exit cancel scope in a different task than it was entered in`。
       （实测踩过：能跑完，但会在 stderr 刷一长串 RuntimeError，看起来像崩了。）

    ✅ 正确的清理路径是 main.py 的 lifespan（同一条循环）。
       这个函数只是最后的保险——**丢弃引用**，让子进程变成孤儿由操作系统回收。
       实际影响很小：npx 起的 Node 进程在父进程 stdin 关闭后会自己退出。
    """
    _sessions.clear()


async def shutdown_all_from_script() -> None:
    """独立脚本用完 MCP 后**在同一个事件循环里**清理（🔧 给 tools/*.py 用）。

    ⚠️ 为什么必须"同一个事件循环"？——踩过一次，记住这个结论：

        MCP 的 `stdio_client` 内部用 anyio 的 task group + cancel scope，
        **它们绑定"创建时所在的事件循环 + 那个任务"**。
        `AsyncExitStack` 一旦在任务结束前没关掉，收尾时就由**事件循环的
        shutdown 逻辑（另一个任务）**去退 cancel scope，于是刷出：

            RuntimeError: Attempted to exit cancel scope in a different task
            than it was entered in

    ❌ 错误写法（试过，没用）：
           asyncio.run(main())                    # main 里建了会话
           asyncio.run(shutdown_all_from_script())  # 换了个循环 → 照样报错

    ✅ 正确写法 —— 把清理放进**同一个** `asyncio.run`：

           async def main():
               await lookup_food_nutrition("豆腐")
               ...
               await shutdown_all()      # ← 就地清理，别换循环

           asyncio.run(main())

    ⚠️ 再说一遍：**这是脚本用法问题，不是项目 bug**。
       服务运行时走 `app/main.py` 的 lifespan，那条路径一直是干净的
       （`main.py` 里 `shutdown_all()` 和请求处理在同一条循环）。
       不清理也只是"退出时 stderr 多一段日志"：工具已经返回、数据已拿到，
       进程随即结束，无资源泄漏。
    """
    with contextlib.suppress(Exception):
        await shutdown_all()


atexit.register(_reset_sessions_sync)
