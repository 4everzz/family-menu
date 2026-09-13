"""pytest 公共夹具（fixture）。

夹具就是"测试开始前准备好的东西"。这里准备两样：
    1. 一个测试客户端（直接调应用内部，不走真实网络端口）；
    2. 一个"以临时用户身份登录"的工厂，用来造出多个不同用户，
       从而测试多用户协作与权限边界。

为什么登录工厂要放在这里、而不是每个测试文件各写一份？
    因为"怎么造出一个用户"这件事是可能变的（将来也许换登录方式）。
    放在公共位置只改一处；各写一份的话，改的时候一定会漏，
    然后出现"某个测试文件莫名其妙全挂"的情况。
"""

# 必须在导入任何会创建事件循环的东西之前完成策略设置，
# 否则 Windows 上会拿到 ProactorEventLoop，导致数据库连接直接失败。
from app.core.event_loop import apply_selector_loop_policy

apply_selector_loop_policy()

from collections.abc import AsyncGenerator, Awaitable, Callable  # noqa: E402
from uuid import uuid4  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.config import settings  # noqa: E402
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


@pytest_asyncio.fixture
async def login_as(
    client: AsyncClient,
    monkeypatch,
) -> Callable[[str], Awaitable[tuple[str, int]]]:
    """返回一个"以临时用户身份登录"的函数，调用后得到 (访问令牌, 用户 ID)。

    开发模式下后端会用 settings.auth_dev_openid 这个固定值来建用户，
    所以每次调用前把它改掉，就等于凭空造出了一个全新用户。
    这样一个测试里就能同时扮演"创建者""家人""陌生人"三种角色。

    参数 prefix 只是让 openid 好认——排查测试残留数据时，一眼能看出是哪条用例造的。
    """

    async def _login(prefix: str) -> tuple[str, int]:
        monkeypatch.setattr(settings, "auth_dev_mode", True)
        monkeypatch.setattr(settings, "auth_dev_openid", f"test_{prefix}_{uuid4().hex[:8]}")

        response = await client.post("/api/v1/auth/login", json={"code": "test-code"})
        assert response.status_code == 200, response.text

        data = response.json()["data"]
        return data["token"], data["user"]["id"]

    return _login
