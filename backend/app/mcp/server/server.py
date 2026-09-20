"""MCP Server：把本项目的只读能力暴露给外部 AI 客户端。

这个模块负责**协议层**——声明有哪些工具、把协议来的参数转交给 `tools.py`、
把结果或错误包成 MCP 要的形状。业务逻辑一行都不在这里。

═══════════════════════════════════════════════════════════════════════
⚠️⚠️ stdout 是 JSON-RPC 通道，绝对不能往里 print() 任何东西 ⚠️⚠️
═══════════════════════════════════════════════════════════════════════
  stdio 传输模式下，Server 和 Client 通过标准输入/输出交换 JSON-RPC 报文。
  混进去一行 `print("debug")`，客户端解析到那行不是合法 JSON，
  整个连接就会断（报错信息通常还很含糊，像是连接被关掉了）。
  **所有日志必须走 stderr**——这就是下面 logging 配到 stderr 的原因，
  也是为什么这个文件里一个 print 都没有。

  Bash 里手工跑本文件调试时，记得把 stderr 和 stdout 分开看，不要合流重定向成 2>&1。

═══════════════════════════════════════════════════════════════════════
⚠️ Windows 上 stdio 默认是 GBK，不是 UTF-8
═══════════════════════════════════════════════════════════════════════
  MCP 协议规定用 UTF-8。Windows 的 Python 在管道模式下的默认编码
  跟着系统区域走（中文系统是 GBK），中文菜名传过来就会解码失败
  或者变成乱码。所以 import 之后就立刻把三个流全设成 UTF-8。

用法（手工调试）：
    cd E:\\AI\\menu\\backend
    ./.venv/Scripts/python.exe run_mcp_server.py

接到 Claude Desktop / Cursor 里时，是让它去启动这个脚本（见 README 的 MCP 一节）。
"""

from __future__ import annotations

import asyncio
import logging
import sys

# ⚠️ 必须在 import 任何 mcp 相关模块之前改编码——
#    否则 mcp 库初始化时读到的还是 GBK。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")

import mcp.types as types  # noqa: E402  （必须在改完编码之后 import）
from mcp.server import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402

from app.core.event_loop import apply_selector_loop_policy  # noqa: E402
from app.core.exceptions import BusinessError  # noqa: E402
from app.mcp.server import tools  # noqa: E402

# ⚠️ 日志走 stderr。走 stdout 会污染 JSON-RPC 通道，客户端直接断连。
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="[mcp-server] %(levelname)s %(message)s",
)
logger = logging.getLogger("family_menu.mcp_server")


# ============================================================================
# 工具声明
# ============================================================================
#
# inputSchema 是 JSON Schema：告诉模型这个工具要什么参数、哪些必填。
# 它的质量直接决定模型用得对不对——**description 写清楚比代码写得好更重要**，
# 因为模型只看得到这段文字，看不到实现。

_TOKEN_PROPERTY = {
    "type": "string",
    "description": (
        "访问令牌。在「小家智膳」App 中登录后获得，"
        "格式是一长串字符（JWT）。不同用户看到对方的数据会被拒绝。"
    ),
}

_SPACE_ID_PROPERTY = {
    "type": "integer",
    "description": "家庭组 ID。用户可以在 App 的「我的」页面看到自己所在的家庭组编号。",
}

_TOOL_DEFINITIONS: list[types.Tool] = [
    types.Tool(
        name="list_fridge_items",
        description=(
            "列出某个家庭组冰箱里的所有食材，包含数量、单位、分类、存放位置和保质期。"
            "适合回答「我家冰箱里有什么」「还有鸡蛋吗」这类问题。"
            "支持按分类、存放位置和关键词筛选。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token": _TOKEN_PROPERTY,
                "space_id": _SPACE_ID_PROPERTY,
                "category": {
                    "type": "string",
                    "description": "按分类筛选，例如「蔬菜」「肉类」。不传表示不限。",
                },
                "storage": {
                    "type": "string",
                    "description": "按存放位置筛选，例如「冷藏」「冷冻」「常温」。不传表示不限。",
                },
                "keyword": {
                    "type": "string",
                    "description": "按食材名或备注模糊搜索。不传表示不限。",
                },
            },
            "required": ["token", "space_id"],
        },
    ),
    types.Tool(
        name="get_expiring_items",
        description=(
            "列出即将过期或已经过期的食材，按紧急程度排序（最急的在最前）。"
            "适合回答「有什么快过期了」「冰箱里什么该赶紧吃」。"
            "返回值里 days_left 为负数表示已经过期了几天。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token": _TOKEN_PROPERTY,
                "space_id": _SPACE_ID_PROPERTY,
                "days": {
                    "type": "integer",
                    "description": "往后看几天，默认 7。已过期的食材始终包含在内。",
                    "default": 7,
                },
            },
            "required": ["token", "space_id"],
        },
    ),
    types.Tool(
        name="list_recipes",
        description=(
            "列出某个家庭组菜单里的菜谱，包含菜名、所属分类、做法说明和可选辣度。"
            "适合回答「我家菜单上有什么菜」「有没有清淡的菜」这类问题。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token": _TOKEN_PROPERTY,
                "space_id": _SPACE_ID_PROPERTY,
                "category_id": {
                    "type": "integer",
                    "description": "按分类 ID 筛选。先用 list_categories 拿到分类 ID。不传表示不限。",
                },
                "keyword": {
                    "type": "string",
                    "description": "按菜名模糊搜索。不传表示不限。",
                },
            },
            "required": ["token", "space_id"],
        },
    ),
    types.Tool(
        name="list_categories",
        description=(
            "列出某个家庭组的菜单分类，以及每个分类下有几道菜。"
            "用户的问题比较宽泛（比如「这周吃什么」）时，先调这个把范围收敛，"
            "再用返回的分类 ID 去调 list_recipes。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token": _TOKEN_PROPERTY,
                "space_id": _SPACE_ID_PROPERTY,
            },
            "required": ["token", "space_id"],
        },
    ),
]

#: 工具名 → 实现函数。
#: 单独一张表而不是在 handler 里写 if/elif，是为了让「声明」和「实现」一一对应，
#: 少一个实现或者多写一个名字，从这张表一眼就能看出来。
_TOOL_HANDLERS = {
    "list_fridge_items": tools.list_fridge_items,
    "get_expiring_items": tools.get_expiring_items,
    "list_recipes": tools.list_recipes,
    "list_categories": tools.list_categories,
}


# ============================================================================
# Server
# ============================================================================

server: Server = Server("family-menu")


@server.list_tools()
async def _handle_list_tools() -> list[types.Tool]:
    """回答「你有哪些工具」——客户端启动时会先问这个。"""
    return _TOOL_DEFINITIONS


@server.call_tool()
async def _handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """执行一个工具调用。

    返回的必须是一组 content block（这里是文本），MCP 协议不接受裸字典。
    我们把结果序列化成 JSON 字符串塞进 text —— 模型读 JSON 毫无障碍，
    而且这样结构清晰，比拍平成一句人话更好用（模型能拿到具体字段去做后续推理）。

    ⚠️ 这里**不抛异常到协议层**。工具失败也返回正常结果，
    只是内容里带 `"ok": false` 和原因。
    为什么：协议层报错在客户端看来是「工具坏了」，模型拿不到原因也没法转述；
    而结构化失败模型能读懂（"你不是这个家的成员"），可以自然地告诉用户怎么办。
    """
    if name not in _TOOL_HANDLERS:
        # 名字对不上：这确实是我们两边不一致（客户端问了不存在的工具），
        # 属于开发期问题，如实回报
        payload = {"ok": False, "error": f"未知的工具：{name}"}
        return [types.TextContent(type="text", text=_dump(payload))]

    handler = _TOOL_HANDLERS[name]
    try:
        result = await handler(**(arguments or {}))
    except TypeError as error:
        # 参数名/数量对不上。多半是模型传错了参数名，说清楚它才能自己改过来
        logger.info("工具参数不匹配 | tool=%s | %s", name, error)
        return [
            types.TextContent(
                type="text",
                text=_dump({
                    "ok": False,
                    "error": f"参数不正确：{error}。请检查参数名和是否缺少必填项。",
                }),
            )
        ]
    except Exception as error:  # noqa: BLE001  —— 工具边界，必须全兜住
        # ⚠️ 分两级记录，因为**这里的异常绝大多数是用户输入问题，不是程序 bug**：
        #   令牌过期、不是这家人、家庭组 ID 写错——这些每天都会发生，
        #   如果一律打完整堆栈，stderr 会被淹没，真正需要排查的代码错误反而看不见。
        #   所以：预期内的失败记一句 info；没预料到的才打堆栈。
        if isinstance(error, (tools.ToolAuthError, BusinessError)):
            logger.info("工具调用被拒绝 | tool=%s | %s", name, error)
            payload = {"ok": False, "error": str(error)}
        else:
            logger.exception("工具执行失败（未预期） | tool=%s", name)
            payload = {"ok": False, "error": tools.describe_error(error)}
        return [types.TextContent(type="text", text=_dump(payload))]

    return [types.TextContent(type="text", text=_dump(result))]


def _dump(payload: dict) -> str:
    """把结果序列化成 JSON 文本。

    `ensure_ascii=False` 让中文原样输出——否则中文菜名会变成
    `\\u7ea2\\u70e7\\u8089` 这种转义，虽然合法但白白多占一倍 token，
    而且人手工调试时完全没法看。`default=str` 兜住漏网的日期等类型。
    """
    import json

    return json.dumps(payload, ensure_ascii=False, default=str)


# ============================================================================
# 入口
# ============================================================================


async def main() -> None:
    """跑起来，通过 stdio 和客户端对话。"""
    logger.info("MCP Server 启动 | 工具数=%d", len(_TOOL_DEFINITIONS))
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
    logger.info("MCP Server 已退出")


if __name__ == "__main__":
    # ⚠️ 和 FastAPI 那边同一个坑：psycopg 的异步驱动在 Windows 的默认事件循环
    #    （ProactorEventLoop）上跑不起来，必须换成 Selector。
    #    这个 Server 会查数据库，所以同样要设。
    apply_selector_loop_policy()
    asyncio.run(main())
