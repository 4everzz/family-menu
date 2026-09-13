"""pytest 公共夹具（fixture）。

夹具就是"测试开始前准备好的东西"。这里准备的是一个测试客户端。
"""

# 必须在导入任何会创建事件循环的东西之前完成策略设置，
# 否则 Windows 上会拿到 ProactorEventLoop，导致数据库连接直接失败。
from app.core.event_loop import apply_selector_loop_policy

apply_selector_loop_policy()

from collections.abc import AsyncGenerator  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """直连应用的测试客户端。

    使用 ASGITransport 不经过真实网络端口，直接调用应用内部，
    测试更快、也不会因为端口被占用而失败。

    注意：这里连接的是 .env 里配置的开发数据库，
    所以测试产生的数据会落在 family_menu 库里（本地开发环境可接受）。
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
