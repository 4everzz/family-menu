"""设置 / 修改账号凭据（用户名、密码）的测试。

⭐ 这一组测试守的是"账号能不能自救"这件事：
   在此之前**注册之后就再也改不了密码**——用户被撞库了都没法换密码。
   另外微信登录进来的用户（没有用户名、没有密码）一直没法改用账号密码登录，
   代码里那句"将来在「我的」里补设一套账号密码"挂了很久（auth_service.py 旧注释）。

所以这里测的不只是"接口通不通"，而是几个**闭环**：
   补设之后**真的能用新账号密码登录**；改完密码之后**旧密码真的失效了**。
只断言 200 是不够的——写库成功但登录链路对不上（比如用户名没归一化、
哈希存错字段）是完全可能的。
"""

from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token
from app.models.user import DEFAULT_NICKNAME, User
from app.repositories.user_repo import UserRepository
from tests.conftest import TEST_PASSWORD

CREDENTIALS_URL = "/api/v1/auth/me/credentials"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/users/me"

#: 测试里统一用这个新密码。抽出来是为了让"新密码 ≠ 旧密码"这件事一眼能看见。
NEW_PASSWORD = "BrandNew456"


def _auth(token: str) -> dict[str, str]:
    """构造带令牌的请求头。"""
    return {"Authorization": f"Bearer {token}"}


async def _create_passwordless_user() -> int:
    """造一个"只有微信身份、没有用户名密码"的用户，返回其 id。

    为什么不走 /auth/login/wechat？
        那条路要真去调微信接口换 openid，单测里既慢又不可控（要 mock 外部 HTTP）。
        这里要测的是"补设凭据"这件事本身，用户是怎么来的并不重要，
        所以直接写库——这也更贴近真实形态（老用户本来就是这么躺在库里的）。
    """
    async with AsyncSessionLocal() as session:
        user = User(nickname=DEFAULT_NICKNAME)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


async def _username_of(client: AsyncClient, token: str) -> str:
    """取当前登录用户的用户名。

    `login_as` 夹具只回令牌和 id（用户名是随机生成的，拿不到），
    所以要改用户名/验证登录就得先把它读出来。
    """
    response = await client.get(ME_URL, headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]["username"]


async def _try_login(client: AsyncClient, username: str, password: str):
    """真去登一次，返回响应对象。"""
    return await client.post(LOGIN_URL, json={"username": username, "password": password})


# ============================================================================
# 首次设置（微信登录进来的用户补一套账号密码）
# ============================================================================


class TestFirstTimeSetup:
    """没有用户名密码的用户，第一次把自己的账号建出来。"""

    async def test_setup_then_can_login_with_new_credentials(self, client: AsyncClient) -> None:
        """⭐ 核心闭环：补设成功之后，必须真的能用这套账号密码登录。

        只断言接口返回 200 是不够的——那只能说明"写库没报错"。
        用户名归一化、密码哈希落到正确的字段，这两件事只有真去登录一次才验得出来。
        """
        user_id = await _create_passwordless_user()
        token = create_access_token(user_id)

        response = await client.patch(
            CREDENTIALS_URL,
            json={
                "username": "FreshUser01",
                "password": NEW_PASSWORD,
                "password_confirm": NEW_PASSWORD,
            },
            headers=_auth(token),
        )
        assert response.status_code == 200, response.text
        # 用户名要归一化成小写（和注册保持一致，否则"输入法首字母大写就登不进"）
        assert response.json()["data"]["username"] == "freshuser01"

        login = await _try_login(client, "FreshUser01", NEW_PASSWORD)
        assert login.status_code == 200, login.text
        assert login.json()["data"]["user"]["id"] == user_id

    async def test_setup_requires_both_username_and_password(self, client: AsyncClient) -> None:
        """只给用户名、或只给密码 → 都拒绝。

        ⚠️ 为什么不能"设一半"：只设用户名，用户没密码还是登不了；
           只设密码，没有登录名那密码也没处用。
           允许这种中间态，用户会以为设好了、然后一直登不进去，且完全不知道差什么。
        """
        user_id = await _create_passwordless_user()
        token = create_access_token(user_id)

        only_username = await client.patch(
            CREDENTIALS_URL, json={"username": "halfway01"}, headers=_auth(token)
        )
        assert only_username.status_code == 400, only_username.text
        assert "同时设置" in only_username.json()["message"]

        only_password = await client.patch(
            CREDENTIALS_URL,
            json={"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD},
            headers=_auth(token),
        )
        assert only_password.status_code == 400, only_password.text

    async def test_setup_rejects_taken_username(self, client: AsyncClient, login_as) -> None:
        """别人已经占了的用户名不能用——这条在注册时也有，两处规则必须一致。"""
        _, other_id = await login_as("owner")
        async with AsyncSessionLocal() as session:
            taken = (await session.get(User, other_id)).username

        user_id = await _create_passwordless_user()
        token = create_access_token(user_id)
        response = await client.patch(
            CREDENTIALS_URL,
            json={"username": taken, "password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD},
            headers=_auth(token),
        )
        assert response.status_code == 400, response.text
        assert response.json()["code"] == 1009  # CODE_USERNAME_TAKEN

    async def test_setup_rejects_bad_username_format(self, client: AsyncClient) -> None:
        """用户名格式规则复用注册那套（只允许字母数字下划线）。"""
        user_id = await _create_passwordless_user()
        token = create_access_token(user_id)
        response = await client.patch(
            CREDENTIALS_URL,
            json={"username": "中文不行", "password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD},
            headers=_auth(token),
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == 1002  # CODE_PARAM_INVALID


# ============================================================================
# 改密码
# ============================================================================


class TestChangePassword:
    """已有账号的改密码流程。"""

    async def test_requires_current_password(self, client: AsyncClient, login_as) -> None:
        """不带当前密码 → 拒绝。

        ⚠️ 这条是"手机被别人拿到"的防线：没有它，任何人捡到一台已登录的手机
           就能直接把密码改掉、把账号据为己有。
        """
        token, _ = await login_as("nocur")
        response = await client.patch(
            CREDENTIALS_URL,
            json={"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD},
            headers=_auth(token),
        )
        assert response.status_code == 400, response.text
        assert "当前密码" in response.json()["message"]

    async def test_wrong_current_password_rejected(self, client: AsyncClient, login_as) -> None:
        """当前密码不对 → 拒绝。"""
        token, _ = await login_as("wrongcur")
        response = await client.patch(
            CREDENTIALS_URL,
            json={
                "password": NEW_PASSWORD,
                "password_confirm": NEW_PASSWORD,
                "current_password": "NotTheRightOne1",
            },
            headers=_auth(token),
        )
        assert response.status_code == 400, response.text
        assert response.json()["code"] == 1010  # CODE_BAD_CREDENTIALS

    async def test_old_password_dies_new_one_works(self, client: AsyncClient, login_as) -> None:
        """⭐ 闭环：改完密码之后，旧密码必须失效、新密码必须能用。

        只验一边都不够：只验"新密码能用"可能掩盖"旧密码也还能用"（根本没改掉）；
        只验"旧密码失效"可能是这次改成了别的什么值。
        """
        token, _ = await login_as("rotate")
        username = await _username_of(client, token)

        changed = await client.patch(
            CREDENTIALS_URL,
            json={
                "password": NEW_PASSWORD,
                "password_confirm": NEW_PASSWORD,
                "current_password": TEST_PASSWORD,
            },
            headers=_auth(token),
        )
        assert changed.status_code == 200, changed.text

        old = await _try_login(client, username, TEST_PASSWORD)
        assert old.status_code == 400, "旧密码不该还能登录"
        new = await _try_login(client, username, NEW_PASSWORD)
        assert new.status_code == 200, new.text

    async def test_new_password_too_short_rejected(self, client: AsyncClient, login_as) -> None:
        """密码长度规则复用注册那套（同一个函数，不是抄一份）。"""
        token, _ = await login_as("shortpw")
        response = await client.patch(
            CREDENTIALS_URL,
            json={"password": "abc", "password_confirm": "abc", "current_password": TEST_PASSWORD},
            headers=_auth(token),
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == 1002

    async def test_password_cannot_equal_username(self, client: AsyncClient, login_as) -> None:
        """密码不能和用户名相同（撞库时这种账号最先失守）。

        ⚠️ 这条只能在服务层判：这次可能没改用户名，
           但把密码改成了**老的**用户名——请求模型看不见"当前用户名是什么"。
        """
        token, _ = await login_as("sameasuser")
        username = await _username_of(client, token)

        response = await client.patch(
            CREDENTIALS_URL,
            json={
                "password": username,
                "password_confirm": username,
                "current_password": TEST_PASSWORD,
            },
            headers=_auth(token),
        )
        assert response.status_code == 400, response.text
        assert "不能与用户名相同" in response.json()["message"]

    async def test_confirm_mismatch_rejected(self, client: AsyncClient, login_as) -> None:
        """两次新密码不一致 → 拒绝（前端那个确认框只是体验，服务端必须再比一次）。"""
        token, _ = await login_as("mismatch")
        response = await client.patch(
            CREDENTIALS_URL,
            json={
                "password": NEW_PASSWORD,
                "password_confirm": "AnotherOne789",
                "current_password": TEST_PASSWORD,
            },
            headers=_auth(token),
        )
        assert response.status_code == 422, response.text
        assert "不一致" in response.json()["message"]


# ============================================================================
# 改用户名
# ============================================================================


class TestChangeUsername:
    """改用户名。"""

    async def test_old_username_stops_working(self, client: AsyncClient, login_as) -> None:
        """⭐ 闭环：改完用户名之后，旧用户名不能再登录、新用户名可以。"""
        token, _ = await login_as("rename")
        old_username = await _username_of(client, token)

        changed = await client.patch(
            CREDENTIALS_URL,
            json={"username": "RenamedUser9", "current_password": TEST_PASSWORD},
            headers=_auth(token),
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["data"]["username"] == "renameduser9"

        old = await _try_login(client, old_username, TEST_PASSWORD)
        assert old.status_code == 400, "旧用户名不该还能登录"
        new = await _try_login(client, "renameduser9", TEST_PASSWORD)
        assert new.status_code == 200, new.text

    async def test_changing_to_same_username_is_allowed(self, client: AsyncClient, login_as) -> None:
        """用户名没变（和现在一样）→ 不算错。

        用户可能只想改密码、顺手把用户名也带上；这时不该报"用户名已被占用"
        （查重时查到的是他自己）。允许它，并且不写无意义的库。
        """
        token, _ = await login_as("same")
        username = await _username_of(client, token)

        response = await client.patch(
            CREDENTIALS_URL,
            json={"username": username, "current_password": TEST_PASSWORD},
            headers=_auth(token),
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["username"] == username


# ============================================================================
# 边界与防护
# ============================================================================


class TestGuards:
    """不该被绕过的地方。"""

    async def test_requires_login(self, client: AsyncClient) -> None:
        """未登录 → 401。身份只能从令牌来。"""
        response = await client.patch(
            CREDENTIALS_URL,
            json={"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD},
        )
        assert response.status_code == 401, response.text

    async def test_empty_payload_rejected(self, client: AsyncClient, login_as) -> None:
        """什么都不传 → 明确拒绝。

        不能让一次"成功的空操作"悄悄返回 200，那会让前端以为改成功了。
        """
        token, _ = await login_as("empty")
        response = await client.patch(CREDENTIALS_URL, json={}, headers=_auth(token))
        assert response.status_code == 422, response.text
        assert "没有要修改的内容" in response.json()["message"]

    async def test_old_token_still_works_after_password_change(
        self, client: AsyncClient, login_as
    ) -> None:
        """⚠️ 这条记录的是一个**已知限制**，不是"期望的正确行为"。

        我们的令牌是无状态 JWT、没有版本号，签出去就管到过期为止，
        所以改密码**不会**让已经发出去的旧令牌失效。

        之所以明写成测试，是为了把这个行为**钉住**：
        将来如果有人加上了令牌失效机制（比如 token 版本号），这条会变红——
        那时候应该把它改成"断言旧令牌失效"，而不是顺手删掉。
        """
        token, _ = await login_as("stale_token")
        changed = await client.patch(
            CREDENTIALS_URL,
            json={
                "password": NEW_PASSWORD,
                "password_confirm": NEW_PASSWORD,
                "current_password": TEST_PASSWORD,
            },
            headers=_auth(token),
        )
        assert changed.status_code == 200, changed.text

        still_ok = await client.get(ME_URL, headers=_auth(token))
        assert still_ok.status_code == 200, "已知限制：改密码目前不会让旧令牌失效"


async def test_credentials_endpoint_is_reachable(client: AsyncClient) -> None:
    """端点确实注册上了（防止改路由时把它弄丢）。

    ⚠️ 未登录时应当是 401 而不是 404 —— 404 说明路由没了，
       401 才是"路由在，只是没带令牌"。
    """
    response = await client.patch(CREDENTIALS_URL, json={})
    assert response.status_code == 401, f"期望 401（路由在但没令牌），实际 {response.status_code}"


async def test_concurrent_username_conflict_returns_friendly_error(
    client: AsyncClient,
    login_as,
    monkeypatch,
) -> None:
    """并发改名撞上唯一索引时，应返回用户名占用提示而不是 500。"""
    first_token, _ = await login_as("rename-race-a")
    second_token, _ = await login_as("rename-race-b")

    # 先让第一个用户占用目标用户名。
    target_username = "racewinner01"
    winner = await client.post(
        CREDENTIALS_URL,
        json={"username": target_username, "current_password": TEST_PASSWORD},
        headers=_auth(first_token),
    )
    assert winner.status_code == 200, winner.text

    # 模拟两个请求并发查重时，第二个请求读到了旧快照、误以为用户名仍空闲。
    # 随后的真实 UPDATE 会撞上 PostgreSQL 唯一索引，从而稳定覆盖并发冲突分支。
    original_lookup = UserRepository.get_by_username

    async def stale_lookup(repository: UserRepository, username: str):
        if username == target_username:
            return None
        return await original_lookup(repository, username)

    monkeypatch.setattr(UserRepository, "get_by_username", stale_lookup)

    loser = await client.post(
        CREDENTIALS_URL,
        json={"username": target_username, "current_password": TEST_PASSWORD},
        headers=_auth(second_token),
    )
    assert loser.status_code == 400, loser.text
    assert loser.json()["code"] == 1009
    assert "已被占用" in loser.json()["message"]

    # 冲突后该连接/事务必须可继续使用，不能留在 SQLAlchemy 的 failed 状态。
    still_valid = await client.get(ME_URL, headers=_auth(second_token))
    assert still_valid.status_code == 200, still_valid.text


async def test_post_alias_behaves_like_patch(client: AsyncClient, login_as) -> None:
    """⭐ POST 兼容入口必须和 PATCH 行为完全一致。

    为什么这条不能省：微信小程序的 `wx.request` 合法 method 里**没有 PATCH**，
    所以前端（`services/http.ts` 也刻意不允许 PATCH）**真正走的是 POST**。
    只测 PATCH 等于没测用户实际会走的那条路。

    （这个模式和 `api/v1/users.py`、`api/v1/user_profile.py` 是一致的：
      后端按标准语义用 PATCH，同时开一个行为相同的 POST 给小程序端。）
    """
    token, _ = await login_as("alias")
    response = await client.post(
        CREDENTIALS_URL,
        json={
            "password": NEW_PASSWORD,
            "password_confirm": NEW_PASSWORD,
            "current_password": TEST_PASSWORD,
        },
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["code"] == 0

    # 走 POST 改完之后同样要能用新密码登录（证明不是"假成功"）
    username = response.json()["data"]["username"]
    login = await _try_login(client, username, NEW_PASSWORD)
    assert login.status_code == 200, login.text
