"""个人资料修改接口测试（PATCH /users/me）。

分两类来看：
    改得对不对 —— 昵称、头像分别能改，部分更新不误伤另一个字段，头像传 null 能重置；
    拦得对不对 —— 空昵称、外部图片地址、未登录、空请求体都该被拒。

接口刻意没有 /users/{user_id} 这种路径：身份只从令牌解析，
前端既不需要也传不了"我要改谁"。这里的用例也顺带守住这一点。
"""

from httpx import AsyncClient

from app.models.user import DEFAULT_NICKNAME

# 上传接口产出的相对路径长这样，头像只接受这种形式
UPLOAD_PATH = "/uploads/2026/09/avatar.png"

# 所有用例都用同一个前缀造账号，login_as 会自动补随机后缀保证不重名
LOGIN_PREFIX = "profile"


def _auth(token: str) -> dict[str, str]:
    """拼鉴权请求头。"""
    return {"Authorization": f"Bearer {token}"}


async def test_update_nickname(client: AsyncClient, login_as) -> None:
    """改昵称：返回值立刻是新昵称，再查一次也是。"""
    token, _ = await login_as(LOGIN_PREFIX)

    response = await client.patch(
        "/api/v1/users/me", json={"nickname": "小明"}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["nickname"] == "小明"

    me = await client.get("/api/v1/users/me", headers=_auth(token))
    assert me.json()["data"]["nickname"] == "小明"


async def test_update_nickname_trims_whitespace(client: AsyncClient, login_as) -> None:
    """昵称首尾的空格会被去掉——手机输入很容易带上看不见的空格。"""
    token, _ = await login_as(LOGIN_PREFIX)

    response = await client.patch(
        "/api/v1/users/me", json={"nickname": "  小明的厨房  "}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["nickname"] == "小明的厨房"


async def test_update_nickname_accepts_chinese(client: AsyncClient, login_as) -> None:
    """昵称可以用中文、表情——限制只在"用户名"上，昵称本来就是给人看的。"""
    token, _ = await login_as(LOGIN_PREFIX)

    response = await client.patch(
        "/api/v1/users/me", json={"nickname": "老张的灶台 🍳"}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["nickname"] == "老张的灶台 🍳"


async def test_update_nickname_rejects_blank(client: AsyncClient, login_as) -> None:
    """只填空格等于没填，要被拒。"""
    token, _ = await login_as(LOGIN_PREFIX)

    response = await client.patch(
        "/api/v1/users/me", json={"nickname": "   "}, headers=_auth(token)
    )

    assert response.status_code == 400
    assert "昵称不能为空" in response.json()["message"]


async def test_update_nickname_rejects_null(client: AsyncClient, login_as) -> None:
    """显式传 null 等于想把昵称删掉——数据库那列是 NOT NULL，不允许。

    错误要是 400 + 一句中文，而不是数据库抛出来的 500。
    """
    token, _ = await login_as(LOGIN_PREFIX)

    response = await client.patch(
        "/api/v1/users/me", json={"nickname": None}, headers=_auth(token)
    )

    assert response.status_code == 400
    assert "昵称不能为空" in response.json()["message"]


async def test_update_avatar_accepts_upload_path(client: AsyncClient, login_as) -> None:
    """头像接受上传接口返回的相对路径。"""
    token, _ = await login_as(LOGIN_PREFIX)

    response = await client.patch(
        "/api/v1/users/me", json={"avatar_url": UPLOAD_PATH}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["avatar_url"] == UPLOAD_PATH


async def test_update_avatar_rejects_external_url(client: AsyncClient, login_as) -> None:
    """头像不接受任意外部地址。

    这个字段最终会进 <image src>，放任外部 URL 等于把"页面上显示什么图"
    的控制权交给别人；而本站上传接口已经做了扩展名白名单 + 文件头魔数 + 大小三重校验。
    """
    token, _ = await login_as(LOGIN_PREFIX)

    response = await client.patch(
        "/api/v1/users/me",
        json={"avatar_url": "https://example.com/somewhere/evil.png"},
        headers=_auth(token),
    )

    assert response.status_code == 400
    assert "头像地址不合法" in response.json()["message"]


async def test_update_avatar_null_resets_to_default(client: AsyncClient, login_as) -> None:
    """头像传 null 表示撤销自定义头像，回到默认占位图。

    这里要区分"没传这个字段"（保持原值）和"显式传 null"（清空）——
    靠 model_dump(exclude_unset=True) 实现，这条用例就是钉住这个行为。
    """
    token, _ = await login_as(LOGIN_PREFIX)

    await client.patch("/api/v1/users/me", json={"avatar_url": UPLOAD_PATH}, headers=_auth(token))
    response = await client.patch(
        "/api/v1/users/me", json={"avatar_url": None}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["avatar_url"] is None


async def test_update_does_not_touch_unsent_fields(client: AsyncClient, login_as) -> None:
    """部分更新：只传昵称时，头像要原样保留。"""
    token, _ = await login_as(LOGIN_PREFIX)

    await client.patch("/api/v1/users/me", json={"avatar_url": UPLOAD_PATH}, headers=_auth(token))
    response = await client.patch(
        "/api/v1/users/me", json={"nickname": "只改名字"}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["nickname"] == "只改名字"
    assert data["avatar_url"] == UPLOAD_PATH


async def test_update_with_empty_body_rejected(client: AsyncClient, login_as) -> None:
    """传空对象（什么都不改）要被拒，而不是静默返回成功。

    静默成功的话，前端漏传字段时用户会以为改好了，实际什么都没发生。
    """
    token, _ = await login_as(LOGIN_PREFIX)

    response = await client.patch("/api/v1/users/me", json={}, headers=_auth(token))

    assert response.status_code == 400
    assert "没有需要修改的内容" in response.json()["message"]


async def test_update_without_token_returns_401(client: AsyncClient) -> None:
    """未登录不能改资料。"""
    response = await client.patch("/api/v1/users/me", json={"nickname": "无名氏"})

    assert response.status_code == 401


async def test_update_via_post_alias(client: AsyncClient, login_as) -> None:
    """小程序端入口（POST）行为必须和 PATCH 完全一致。

    微信小程序的 wx.request 不支持 PATCH，所以后端额外开了一个同行为的 POST。
    两条入口一旦行为不一致，就会出现"小程序上和 App 上表现不同"这种最难查的问题。
    """
    token, _ = await login_as(LOGIN_PREFIX)

    response = await client.post(
        "/api/v1/users/me", json={"nickname": "从小程序改的"}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["nickname"] == "从小程序改的"


async def test_update_only_affects_current_user(client: AsyncClient, login_as) -> None:
    """改资料只影响自己，不会波及别人。

    路径里没有 {user_id}，所以"改别人"这件事从接口形状上就不可能——
    这条用例守的是这个设计不被破坏。
    """
    token_a, _ = await login_as("prof-a")
    token_b, _ = await login_as("prof-b")

    await client.patch("/api/v1/users/me", json={"nickname": "我是 A"}, headers=_auth(token_a))

    me_b = await client.get("/api/v1/users/me", headers=_auth(token_b))
    assert me_b.json()["data"]["nickname"] == DEFAULT_NICKNAME
