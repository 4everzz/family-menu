"""MCP Server 启动入口。

这不是给人直接敲的命令行工具，而是**给 AI 客户端当子进程启动的**：
Claude Desktop、Cursor 这类客户端配置里写一行"用这个脚本启动"，
它们就按 MCP 协议通过标准输入输出和我们对话。

为什么单独一个入口文件、而不是在 app/mcp/server/server.py 里直接 `if __name__`？
  两个原因：
  ① **路径**。写在 app/ 深处时，Python 的模块搜索路径未必包含 backend/，
     客户端从任意工作目录启动都会 import 失败。放在 backend/ 根目录，
     `python run_mcp_server.py` 天然把 backend/ 放进搜索路径，app 包一定 import 得到。
  ② **和 run.py 对称**。后端的另一个入口 run.py 也在这个位置，
     两个入口平级，一眼能看出"这个项目有对外 HTTP 服务和对外 MCP 服务两扇门"。

用法：
    cd E:\\AI\\menu\\backend
    ./.venv/Scripts/python.exe run_mcp_server.py

接入 Claude Desktop（配置文件 claude_desktop_config.json）：
    {
      "mcpServers": {
        "family-menu": {
          "command": "E:\\\\AI\\\\menu\\\\backend\\\\.venv\\\\Scripts\\\\python.exe",
          "args": ["E:\\\\AI\\\\menu\\\\backend\\\\run_mcp_server.py"]
        }
      }
    }

⚠️ 这个进程**不监听任何端口**。stdio 传输意味着它只在父子进程的管道上说话，
   所以不需要开端口、不需要备案，也不会和跑在 8300 的后端抢资源。
   它只在被客户端调起来的时候存在，客户端一关它就跟着退出。

⚠️ 它连的是**同一个数据库**（backend/.env 里的 DATABASE_URL）。
   也就是说外部客户端读到的是真实的家庭数据，改动后端数据库后这里立刻能看到。
   权限走的是同一套 JWT + 成员校验，App 里看不到的东西，这里也看不到。
"""

import sys
from pathlib import Path

# 保证不论从哪个工作目录启动，都能 import 到 app 包。
# （客户端启动子进程时的工作目录是不可控的，这行是必要的保险。）
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.mcp.server.server import main  # noqa: E402

if __name__ == "__main__":
    import asyncio

    from app.core.event_loop import apply_selector_loop_policy  # noqa: E402

    # Windows 上 psycopg 异步不能用默认的 ProactorEventLoop，同上文说明
    apply_selector_loop_policy()
    asyncio.run(main())
