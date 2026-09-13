"""事件循环兼容处理。

为什么需要这个文件？
    Python 在 Windows 上默认使用 ProactorEventLoop，而 psycopg（PostgreSQL 的异步驱动）
    的异步模式不支持它，连接数据库时会直接报：
        InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in async mode

    在 Linux / macOS 上默认就是 SelectorEventLoop，不存在这个问题。
    也就是说：这是"Windows 本地开发"才有的坑，部署到云托管的 Linux 容器后自然消失。
    但为了本地能跑，必须显式把事件循环换成 Selector。

两种使用方式：
    1) 启动服务：uvicorn 支持用"导入字符串"指定事件循环工厂，
       见 run.py 里的 loop="app.core.event_loop:selector_loop_factory"。
    2) 跑测试：见 tests/conftest.py 顶部对全局策略的设置。
"""

import asyncio
import sys


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """uvicorn 的自定义事件循环工厂：返回一个全新的 Selector 事件循环实例。

    这里有一个容易写错的调用约定，说明清楚：
      - 内置名称（如 --loop asyncio）时，uvicorn 会以
        `loop_factory(use_subprocess=...)` 的形式调用它；
      - 但用"自定义导入字符串"时，uvicorn 只是把本函数对象原样交给
        asyncio.Runner，由 Runner 以 `loop_factory()` 无参调用。

    所以本函数必须是"无参、返回循环实例"的形式。
    早期写成"带 use_subprocess 参数、返回循环类"会报
    `BaseEventLoop.create_task() missing 1 required positional argument: 'coro'`，
    因为那样拿到的是类而不是实例。
    """
    return asyncio.SelectorEventLoop()


def apply_selector_loop_policy() -> None:
    """把全局事件循环策略切到 Selector（仅 Windows 需要，其他系统无副作用）。

    适用于"不经过 uvicorn、由测试框架自己创建事件循环"的场景。
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
