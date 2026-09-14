"""注册、登录与鉴权接口测试。

分四层来看，每层挂掉的后果不一样：

    1. 基础设施 —— 服务能起来、数据库连得上；
    2. 鉴权底线 —— 没带令牌或令牌无效一律被拒。这几条如果挂了，等于门没锁；
    3. 自建账号 —— 注册、用户名唯一性、登录，以及"不泄露某个账号是否存在"；
    4. 微信小程序登录 —— 改造前的老用户只有这一条路能进来，不能被改造弄坏。
"""

from uuid import uuid4

from httpx import AsyncClient

from app.core.config import settings
from app.core.password import PASSWORD_MIN_LENGTH
from app.models.user import DEFAULT_NICKNAME, USERNAME_MAX_LENGTH
from tests.conftest import TEST_PASSWORD


def _new_username(tag: str) -> str:
    """生成一个本次运行独有的用户名。

    为什么每次都要带随机后缀？因为测试数据是落在**开发库**里、且不会自动清理的，
    固定名字在第二次跑的时候就会撞上上一轮残留的用户，测试会莫名其妙地挂。
    带上随机后缀，每轮都是干净的新账号（同时也顺带暴露了"测试污染开发库"这个问题）。
    """
    return f"t{tag}_{uuid4().hex[:8]}"


def _register_body(username: str, password: str = TEST_PASSWORD) -> dict:
    """拼一个合法的注册请求体。

    注册现在要求"两次输入的密码一致"，所以 password_confirm 是必填的。
    统一从这里出，免得每个用例各写一遍、漏掉一个就报 422。
    """
    return {"username": username, "password": password, "password_confirm": password}


# ==================== 1. 基础设施 ====================


async def test_health_ok(client: AsyncClient) -> None:
    """健康检查：服务与数据库都正常时返回 ok。"""
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ok"
    assert body["data"]["database"] == "connected"


# ==================== 2. 鉴权底线 ====================


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


# ==================== 3. 自建账号：注册 ====================


async def test_register_succeeds_and_can_access_me(client: AsyncClient) -> None:
    """注册成功后直接拿到令牌，且这个令牌真的能用。"""
    username = _new_username("reg")

    response = await client.post("/api/v1/auth/register", json=_register_body(username))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0

    data = body["data"]
    assert data["token"]
    assert data["expires_in"] > 0
    assert data["user"]["username"] == username
    # 注册不收集昵称，所以一律是默认昵称；头像留空由前端显示占位图
    assert data["user"]["nickname"] == DEFAULT_NICKNAME
    assert data["user"]["avatar_url"] is None

    # 用刚拿到的令牌访问"当前用户"，应当拿到同一个账号
    me_response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {data['token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["data"]["id"] == data["user"]["id"]


async def test_register_ignores_nickname_field(client: AsyncClient) -> None:
    """注册时传了 nickname 也不会生效——个人资料只能在「我的」页改。

    这条是在钉住一个刻意的设计：注册接口**不收**昵称。
    哪天有人"顺手"把 nickname 加回 RegisterRequest，这条会立刻变红。
    """
    response = await client.post(
        "/api/v1/auth/register",
        json={**_register_body(_new_username("nick")), "nickname": "小明的厨房"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["user"]["nickname"] == DEFAULT_NICKNAME


async def test_register_stores_username_in_lowercase(client: AsyncClient) -> None:
    """用户名统一按小写存：大小写混输进去，取回来的应当是小写。"""
    raw = _new_username("case").upper()

    response = await client.post("/api/v1/auth/register", json=_register_body(raw))

    assert response.status_code == 200, response.text
    assert response.json()["data"]["user"]["username"] == raw.lower()


async def test_register_rejects_mismatched_password_confirm(client: AsyncClient) -> None:
    """两次输入的密码不一致要被拒。

    前端那个确认框是"让用户当场发现自己打错了"，属于体验；
    接口是公开的、可以被绕过，所以服务端必须自己再比一次，
    否则库里就可能存下一个"用户以为自己设的是 A、实际是 B"的账号。
    """
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": _new_username("mismatch"),
            "password": TEST_PASSWORD,
            "password_confirm": "AnotherPass456",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == 1002
    assert "两次输入的密码不一致" in response.json()["message"]


async def test_register_rejects_missing_password_confirm(client: AsyncClient) -> None:
    """没传确认密码时给中文提示，而不是 Pydantic 的英文 'Field required'。"""
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": _new_username("noconfirm"), "password": TEST_PASSWORD},
    )

    assert response.status_code == 422
    assert "请再输入一次密码" in response.json()["message"]


async def test_register_rejects_duplicate_username(client: AsyncClient) -> None:
    """同一个用户名不能注册两次——这是唯一性约束最直接的一条。"""
    username = _new_username("dup")

    first = await client.post("/api/v1/auth/register", json=_register_body(username))
    assert first.status_code == 200, first.text

    second = await client.post("/api/v1/auth/register", json=_register_body(username))

    assert second.status_code == 400
    assert second.json()["code"] == 1009
    assert "已被占用" in second.json()["message"]


async def test_register_rejects_duplicate_username_ignoring_case(client: AsyncClient) -> None:
    """大小写不同也算重复。

    如果不做这条，"Tom" 和 "tom" 会是两个账号，
    而人眼根本分不出哪个是哪个——冒充起来太容易了。
    """
    username = _new_username("mix")

    first = await client.post("/api/v1/auth/register", json=_register_body(username))
    assert first.status_code == 200, first.text

    second = await client.post(
        "/api/v1/auth/register", json=_register_body(username.upper())
    )

    assert second.status_code == 400
    assert second.json()["code"] == 1009


async def test_register_rejects_non_ascii_username(client: AsyncClient) -> None:
    """用户名不接受中文等非 ASCII 字符（昵称才允许）。

    挡这类用户名的原因之一是"同形字冒充"：
    Cyrillic 的 а 和 Latin 的 a 看起来一模一样，却是两个不同账号。
    """
    response = await client.post(
        "/api/v1/auth/register",
        json=_register_body(f"张三{uuid4().hex[:4]}"),
    )

    assert response.status_code == 422
    assert response.json()["code"] == 1002
    assert "用户名需为" in response.json()["message"]


async def test_register_rejects_username_with_symbols(client: AsyncClient) -> None:
    """用户名里的短横线、空格、@ 等符号一律不接受。"""
    response = await client.post(
        "/api/v1/auth/register", json=_register_body("bad-name@x")
    )

    assert response.status_code == 422
    assert response.json()["code"] == 1002


async def test_register_rejects_too_long_username(client: AsyncClient) -> None:
    """超过长度上限的用户名要被拦下。"""
    response = await client.post(
        "/api/v1/auth/register",
        json=_register_body("a" * (USERNAME_MAX_LENGTH + 1)),
    )

    assert response.status_code == 422


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    """密码短于下限要被拦下。"""
    response = await client.post(
        "/api/v1/auth/register",
        json=_register_body(_new_username("sp"), "a" * (PASSWORD_MIN_LENGTH - 1)),
    )

    assert response.status_code == 422
    assert "密码至少" in response.json()["message"]


async def test_register_rejects_password_same_as_username(client: AsyncClient) -> None:
    """密码不能和用户名一样——那种账号在撞库时最先失守。"""
    username = "samepass1234"

    response = await client.post("/api/v1/auth/register", json=_register_body(username, username))

    assert response.status_code == 422
    assert "不能与用户名相同" in response.json()["message"]


# ==================== 3. 自建账号：登录 ====================


async def test_login_succeeds_with_correct_password(client: AsyncClient) -> None:
    """注册后能用同一套账号密码登录，拿到的还是同一个账号。"""
    username = _new_username("login")

    registered = await client.post("/api/v1/auth/register", json=_register_body(username))
    assert registered.status_code == 200, registered.text
    registered_id = registered.json()["data"]["user"]["id"]

    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": TEST_PASSWORD}
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["user"]["id"] == registered_id
    assert data["token"]


async def test_login_ignores_username_case(client: AsyncClient) -> None:
    """注册时用的是小写存储，登录时输入大写也应当能进。"""
    username = _new_username("case")

    await client.post("/api/v1/auth/register", json=_register_body(username))

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username.upper(), "password": TEST_PASSWORD},
    )

    assert response.status_code == 200, response.text


async def test_login_with_wrong_password_rejected(client: AsyncClient) -> None:
    """密码错误要被拒。"""
    username = _new_username("wrongpwd")

    await client.post("/api/v1/auth/register", json=_register_body(username))

    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "WrongPass999"}
    )

    assert response.status_code == 400
    assert response.json()["code"] == 1010


async def test_login_does_not_reveal_whether_account_exists(client: AsyncClient) -> None:
    """账号不存在和密码错误，必须给出完全一样的提示。

    如果两者提示不同（"该账号不存在" vs "密码错误"），
    攻击者就能拿一批用户名来试探，从提示语的差别里筛出哪些账号真实存在，
    再只针对存在的那些去爆破。所以这两条既要比状态码、也要比文案。
    """
    username = _new_username("noreveal")

    await client.post("/api/v1/auth/register", json=_register_body(username))

    wrong_password = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "WrongPass999"}
    )
    unknown_account = await client.post(
        "/api/v1/auth/login",
        json={"username": _new_username("ghost"), "password": "WrongPass999"},
    )

    assert wrong_password.status_code == unknown_account.status_code == 400
    assert wrong_password.json()["code"] == unknown_account.json()["code"] == 1010
    assert wrong_password.json()["message"] == unknown_account.json()["message"]


async def test_login_with_empty_password_returns_422(client: AsyncClient) -> None:
    """参数不合法时返回 422，且错误信息是可读的。"""
    response = await client.post(
        "/api/v1/auth/login", json={"username": _new_username("empty"), "password": ""}
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 1002
    assert "参数不合法" in body["message"]


# ==================== 4. 微信小程序登录（保留链路） ====================


async def test_wechat_login_dev_mode_then_access_me(client: AsyncClient, monkeypatch) -> None:
    """开发模式下跑通整条微信登录链路：换 openid → 建号 → 签发令牌 → 访问接口。

    临时打开 AUTH_DEV_MODE，是为了在没有 AppSecret 的环境里也能验证链路本身。
    """
    monkeypatch.setattr(settings, "auth_dev_mode", True)
    monkeypatch.setattr(settings, "auth_dev_openid", f"test_wx_{uuid4().hex[:8]}")

    login_response = await client.post("/api/v1/auth/login/wechat", json={"code": "any-code"})
    assert login_response.status_code == 200, login_response.text

    data = login_response.json()["data"]
    assert data["token"]
    assert data["user"]["id"] > 0
    # 微信自动建号的用户还没有用户名，只能从小程序进来
    assert data["user"]["username"] is None

    me_response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {data['token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["data"]["id"] == data["user"]["id"]


async def test_wechat_login_same_openid_returns_same_user(client: AsyncClient, monkeypatch) -> None:
    """同一个 openid 重复登录，应当复用已有账号而不是重复建号。

    这条是"身份绑定表"的核心保证：同一个微信身份只能指向一个账号。
    """
    monkeypatch.setattr(settings, "auth_dev_mode", True)
    monkeypatch.setattr(settings, "auth_dev_openid", f"test_wx_{uuid4().hex[:8]}")

    first = await client.post("/api/v1/auth/login/wechat", json={"code": "code-a"})
    second = await client.post("/api/v1/auth/login/wechat", json={"code": "code-b"})

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["user"]["id"] == second.json()["data"]["user"]["id"]


async def test_wechat_login_empty_code_returns_422(client: AsyncClient) -> None:
    """code 为空属于参数问题，不该跑到调微信那一步。"""
    response = await client.post("/api/v1/auth/login/wechat", json={"code": ""})

    assert response.status_code == 422
    assert response.json()["code"] == 1002
