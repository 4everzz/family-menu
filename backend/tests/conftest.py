"""pytest 公共夹具（fixture）。

夹具就是"测试开始前准备好的东西"。这里准备两样：
    1. 一个测试客户端（直接调应用内部，不走真实网络端口）；
    2. 一个"注册一个全新用户并登录"的工厂，用来造出多个不同用户，
       从而测试多用户协作与权限边界。

为什么登录工厂要放在这里、而不是每个测试文件各写一份？
    因为"怎么造出一个用户"这件事是可能变的（将来也许会多一种登录方式）。
    放在公共位置只改一处；各写一份的话，改的时候一定会漏，
    然后出现"某个测试文件莫名其妙全挂"的情况。
"""

# 必须在导入任何会创建事件循环的东西之前完成策略设置，
# 否则 Windows 上会拿到 ProactorEventLoop，导致数据库连接直接失败。
from app.core.event_loop import apply_selector_loop_policy

apply_selector_loop_policy()

import re  # noqa: E402
from collections.abc import AsyncGenerator, Awaitable, Callable  # noqa: E402
from uuid import uuid4  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app  # noqa: E402

# 测试账号统一使用这个密码。抽成常量，将来密码规则变了只改这一处。
TEST_PASSWORD = "TestPass123"

# 用户名上限是 20 位（见 app/models/user.py）。
# 这里把"可读前缀"截断到 10 位，剩下的位置留给 1 个下划线 + 8 位随机后缀，
# 保证自动生成的名字一定是合法的、且不同测试之间不会撞名。
_PREFIX_MAX_LENGTH = 10
_RANDOM_SUFFIX_LENGTH = 8


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """直连应用的测试客户端。

    使用 ASGITransport 不经过真实网络端口，直接调用应用内部，
    测试更快、也不会因为端口被占用而失败。

    ⚠️ 这里连接的是 .env 里配置的开发数据库，测试数据会真的落进 family_menu 库，
       而且目前**不会自动清理**——跑得越多，库里的测试用户就越多。
       要根治得单独准备一个测试库，这属于独立的一件事，先在这里记着。
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def login_as(
    client: AsyncClient,
) -> Callable[[str], Awaitable[tuple[str, int]]]:
    """返回一个"注册并登录一个全新用户"的函数，调用后得到 (访问令牌, 用户 ID)。

    为什么改成"真去注册"，而不是像以前那样靠 AUTH_DEV_MODE 伪造一个 openid？
        伪造出来的用户永远绕过了注册链路，于是注册那套最该被测的逻辑
        ——用户名唯一性、格式校验、密码哈希——在整套测试里一次都没跑过。
        改成真注册之后，各个测试文件里的多用户场景顺带也覆盖了注册接口。

    参数 prefix 只是让用户名好认：排查测试残留数据时，一眼能看出是哪条用例造的。
    前缀里可能带短横线（例如 "case-owner"），而用户名只允许字母数字下划线，所以要替换掉。
    """

    async def _register(prefix: str) -> tuple[str, int]:
        safe_prefix = re.sub(r"[^A-Za-z0-9_]", "_", prefix)[:_PREFIX_MAX_LENGTH]
        username = f"{safe_prefix}_{uuid4().hex[:_RANDOM_SUFFIX_LENGTH]}"

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "password": TEST_PASSWORD,
                # 注册要求二次确认（防用户打错），所以两个字段都要给
                "password_confirm": TEST_PASSWORD,
            },
        )
        assert response.status_code == 200, response.text

        data = response.json()["data"]
        return data["token"], data["user"]["id"]

    return _register
