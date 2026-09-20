"""手工验收：像一个真正的 MCP 客户端那样连上我们自己的 Server。

不是 pytest（那个另写），而是"把 Server 当子进程拉起来、走真实协议对话"的端到端检查，
用来确认三件事：
  ① 子进程能起来、握手能完成、工具能列出来；
  ② 拿真实令牌调用能查出真实数据（连的是同一个库）；
  ③ 各类错误路径返回的是"人话"而不是协议层崩掉。

用法：
    cd E:\\AI\\menu\\backend
    ./.venv/Scripts/python.exe -m tools.check_mcp_server

⚠️ 注意：这个脚本用的是**官方 mcp SDK 的 stdio_client**（外面那侧），
   和 app/mcp/gateway.py 的客户端是两套独立实现——这里不碰项目的会话单例，
   所以不存在"跨事件循环清理"的问题（退出时由 SDK 自己收尾，无残留）。
"""

import asyncio
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

from app.core.event_loop import apply_selector_loop_policy  # noqa: E402
from app.core.security import create_access_token  # noqa: E402

PYTHON = str(BACKEND_DIR / ".venv" / "Scripts" / "python.exe")
SERVER = str(BACKEND_DIR / "run_mcp_server.py")

# 真人测试账号 zjy（id 1602），家庭组 1175。见项目记忆。
ZJY_USER_ID = 1602
ZJY_SPACE_ID = 1175


def _show(title: str, payload: str) -> None:
    print(f"\n--- {title} ---")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        print(payload)
        return
    print(json.dumps(data, ensure_ascii=False, indent=2)[:1400])


async def main() -> None:
    params = StdioServerParameters(
        command=PYTHON,
        args=[SERVER],
        env={"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print("✅ 握手成功")
            print("   服务端:", init.serverInfo.name, init.serverInfo.version)
            print("   协议版本:", init.protocolVersion)

            listed = await session.list_tools()
            names = [t.name for t in listed.tools]
            print(f"\n✅ 工具列表（{len(names)} 个）: {names}")
            assert set(names) == {
                "list_fridge_items",
                "get_expiring_items",
                "list_recipes",
                "list_categories",
            }, "工具集合和预期不一致"

            token = create_access_token(ZJY_USER_ID)

            # ---- 正常路径 ----
            r = await session.call_tool("list_categories", {"token": token, "space_id": ZJY_SPACE_ID})
            _show("list_categories（真实数据）", r.content[0].text)

            r = await session.call_tool(
                "list_fridge_items", {"token": token, "space_id": ZJY_SPACE_ID}
            )
            _show("list_fridge_items（真实数据）", r.content[0].text)

            r = await session.call_tool(
                "list_recipes", {"token": token, "space_id": ZJY_SPACE_ID, "keyword": "肉"}
            )
            _show("list_recipes（keyword=肉）", r.content[0].text)

            r = await session.call_tool(
                "get_expiring_items", {"token": token, "space_id": ZJY_SPACE_ID, "days": 30}
            )
            _show("get_expiring_items（days=30）", r.content[0].text)

            # ---- 错误路径：都应该是 ok=false + 人话，而不是协议崩 ----
            r = await session.call_tool(
                "list_fridge_items", {"token": "not-a-real-token", "space_id": ZJY_SPACE_ID}
            )
            _show("错误路径：坏令牌", r.content[0].text)

            r = await session.call_tool("list_fridge_items", {"token": token, "space_id": 99999999})
            _show("错误路径：不存在的家庭组", r.content[0].text)

            r = await session.call_tool("no_such_tool", {"token": token})
            _show("错误路径：未知工具", r.content[0].text)

    print("\n✅ 全部通过")


if __name__ == "__main__":
    apply_selector_loop_policy()
    asyncio.run(main())
