"""登录与鉴权接口测试。

覆盖三个关键行为：
    1. 服务能起来、数据库连得上；
    2. 没带令牌访问受保护接口会被拒绝；
    3. 带令牌能正常访问，并且拿到的是"自己"的数据。
"""

from httpx import AsyncClient

from app.core.config import settings


async def test_health_ok(client: AsyncClient) -> None:
    """健康检查：服务与数据库都正常时返回 ok。"""
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ok"
    assert body["data"]["database"] == "connected"


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    """不带令牌访问受保护接口，必须被拒绝。

    这条测试是安全底线：如果它能通过，说明鉴权形同虚设。
    """
    response = await client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["code"] == 1001


async def test_me_with_invalid_token_returns_401(client: AsyncClient) -> None:
    """令牌被伪造或损坏时，同样必须被拒绝。"""
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer this.is.not.a.valid.token"},
    )

    assert response.status_code == 401


async def test_login_dev_mode_then_access_me(client: AsyncClient, monkeypatch) -> None:
    """开发模式下完成整条登录链路：换 openid → 签发令牌 → 用令牌访问接口。

    这里临时打开 AUTH_DEV_MODE，是为了在没有 AppSecret 的环境中也能验证链路。
    """
    monkeypatch.setattr(settings, "auth_dev_mode", True)

    login_response = await client.post("/api/v1/auth/login", json={"code": "any-code-for-test"})
    assert login_response.status_code == 200

    data = login_response.json()["data"]
    assert data["token"]
    assert data["user"]["id"] > 0
    assert data["expires_in"] > 0

    # 用刚拿到的令牌访问"当前用户"，应当拿到同一个用户
    me_response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {data['token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["data"]["id"] == data["user"]["id"]


async def test_login_same_code_returns_same_user(client: AsyncClient, monkeypatch) -> None:
    """同一个 openid 重复登录，应当复用已有用户而不是重复创建。"""
    monkeypatch.setattr(settings, "auth_dev_mode", True)

    first = await client.post("/api/v1/auth/login", json={"code": "code-a"})
    second = await client.post("/api/v1/auth/login", json={"code": "code-b"})

    assert first.json()["data"]["user"]["id"] == second.json()["data"]["user"]["id"]


async def test_login_empty_code_returns_422(client: AsyncClient) -> None:
    """参数不合法时返回 422，且错误信息是可读的。"""
    response = await client.post("/api/v1/auth/login", json={"code": ""})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 1002
    assert "参数不合法" in body["message"]
