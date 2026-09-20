"""MCP Server 注册表。

集中声明"本项目要连哪些外部 MCP Server"。
**加一个新的外部 Server 只需要改这个文件**，gateway 和业务层都不用动。

为什么单独一个文件？
  因为 MCP 的 Server 定义有三种形态（stdio 起子进程 / sse / streamable-http），
  参数各不相同（命令、参数、环境变量、URL）。把这些声明集中起来，
  好处是：① 一眼能看出项目依赖了哪些外部能力；
        ② 将来某个 Server 要换传输方式，只改这一处；
        ③ 测试时可以整表替换成假的 Server 定义。
"""

from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings


@dataclass(frozen=True)
class McpServerSpec:
    """一个 MCP Server 的连接声明。

    ⚠️ 本项目当前只用 **stdio** 传输（gateway 也只实现了 stdio）。
    为什么不用 sse/http？
      · stdio 不需要额外开端口、不需要处理鉴权和跨域，最省事；
      · 更重要的是——**stdio 模式下 Server 是 client 起的子进程**，
        client 一停子进程就跟着停，不存在"孤儿进程占着端口"的问题。
    将来若要连远程 Server（如公司内网的），再加 `transport` 字段和对应分支。
    """

    #: 逻辑名。业务代码用这个名字引用（如 "food"），不用记具体命令
    name: str
    #: 启动命令。Windows 上 npx 是 .cmd，所以 gateway 会做一次命令归一化
    command: str
    #: 命令参数
    args: list[str] = field(default_factory=list)
    #: 额外环境变量（如某些 Server 需要 API Key）
    env: dict[str, str] = field(default_factory=dict)
    #: 单次工具调用超时（秒）。见下方说明为什么给得比较宽
    timeout: float = 15.0

    def read_write_args(self) -> dict[str, Any]:
        """产出一份传给 `stdio_client` 的参数。

        为什么单独一个方法，而不是把 env 直接在定义里写全：
        这里做的是"**运行时的环境补充**"，和"这个 Server 需要哪些配置"是两件事。
        Server 声明只写它业务上需要的变量（比如 API Key），
        而编码、日志这类**运行环境适配**由这里统一补——
        这样加一个新 Server 时不用再想一遍编码问题，也不会漏。
        """
        env = dict(self.env)

        # ⚠️ Windows：MCP 协议规定 UTF-8，但 Windows 的 Python 子进程默认跟随
        #    系统区域（中文系统 = GBK）。不强制指定的话，Server 那边 print 出来的
        #    中文会解码失败（`UnicodeDecodeError` / 乱码），而且报错点离真正的原因很远。
        #    这两个变量是 Python 自己认的，设了就生效，不用改对方的代码。
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")

        return {
            "command": self.command,
            "args": list(self.args),
            "env": env,
        }


#: 连外部 MCP Server 时用的命令。
#: 默认用 `npx`——它由 MCP Server 分包自己带上运行时，
#: 我们不需要在本项目里装 Node 依赖。
_MCP_NPX = "npx"


def get_server_spec(name: str) -> McpServerSpec | None:
    """按逻辑名取一个 Server 声明；没有就返回 None（调用方自行降级）。"""
    return _SERVERS.get(name)


def list_server_names() -> list[str]:
    """列出所有已注册的 Server 名。给健康检查 / 调试用。"""
    return list(_SERVERS.keys())


# ---------------------------------------------------------------------------
# 已注册的外部 Server
# ---------------------------------------------------------------------------

#: 中国食物成分表。
#:
#: 选它的理由（对比过 USDA 那几个）：
#:   · **中文食物名**——USDA/FoodData Central 里搜不到"排骨""五花肉"，
#:     中文项目接过去等于白接。这个是《中国食物成分表》的数据。
#:   · **数据内置在 npm 包里**，不实时调外部 API → 快、稳、不吃网络。
#:   · **零 API Key**，不需要注册申请。
#:   · MIT 协议，1700+ 种食物 × 25 项营养素（每 100g）。
#:
#: ⚠️ 已知限制（决定了业务层为什么要"两级策略"）：
#:   它是**食材成分表**，不是菜谱库。"排骨""豆腐""鸡蛋"查得到，
#:   "红烧肉""土豆炖牛肉"这种**复合菜查不到**——因为那是烹饪后的产物。
#:   所以 nutrition_service 里做了"先查主料拿基准、再由大模型按烹饪方式修正"。
#:
#: ⚠️ 首次调用的额外成本：
#:   `npx -y` 第一次运行要下载这个包（几十 MB），可能耗时 10 秒以上。
#:   之后有 npx 缓存就快了。这也是 timeout 给到 15 秒、且默认不开启的原因之一。
_FOOD_SERVER = McpServerSpec(
    name="food",
    command=_MCP_NPX,
    args=["-y", "cn-food-mcp"],
    env={},
    # 首次要下载包，给宽一点；正常情况响应在 1 秒内
    timeout=settings.mcp_call_timeout,
)


#: 名字 → 声明。业务代码通过 `get_server_spec("food")` 取用。
_SERVERS: dict[str, McpServerSpec] = {
    _FOOD_SERVER.name: _FOOD_SERVER,
}
