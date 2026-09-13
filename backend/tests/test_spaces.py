"""家庭组接口测试。

覆盖四类行为：
    1. 创建家庭组后，创建者就是管理员，且拿到邀请码；
    2. 家人能凭邀请码加入，加入后成员数正确；
    3. 权限边界：非成员读不到别人家的数据，普通成员拿不到邀请码；
    4. 重复加入、错误邀请码这类边界情况的提示是否合理。

关于测试数据：测试直接跑在本地开发库上，每个用例用随机后缀的临时用户，
所以可以反复运行而不会因为上一次留下的数据而失败。
（随机用户会累积在开发库里，属于可接受的本地测试残留。）
"""

from httpx import AsyncClient


def _auth(token: str) -> dict[str, str]:
    """构造带令牌的请求头。"""
    return {"Authorization": f"Bearer {token}"}


async def test_create_space_makes_creator_admin(client: AsyncClient, login_as) -> None:
    """创建家庭组：创建者角色是管理员，成员数 1，并且拿到邀请码。"""
    token, user_id = await login_as("creator")

    response = await client.post("/api/v1/spaces", json={"name": "张家"}, headers=_auth(token))

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["my_role"] == "admin"
    assert data["owner_id"] == user_id
    assert data["member_count"] == 1
    assert data["invite_code"] and len(data["invite_code"]) == 8


async def test_created_space_appears_in_my_list(client: AsyncClient, login_as) -> None:
    """创建后的家庭组要出现在"我的家庭组"列表里。"""
    token, _ = await login_as("lister")
    await client.post("/api/v1/spaces", json={"name": "我的家"}, headers=_auth(token))

    response = await client.get("/api/v1/spaces", headers=_auth(token))

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["data"]]
    assert "我的家" in names


async def test_join_by_invite_code(client: AsyncClient, login_as) -> None:
    """家人凭邀请码加入：角色是普通成员，成员数变成 2。"""
    owner_token, _ = await login_as("owner")
    created = await client.post("/api/v1/spaces", json={"name": "父母家"}, headers=_auth(owner_token))
    space = created.json()["data"]

    member_token, _ = await login_as("joiner")
    response = await client.post(
        "/api/v1/spaces/join",
        json={"invite_code": space["invite_code"]},
        headers=_auth(member_token),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["id"] == space["id"]
    assert data["my_role"] == "member"
    assert data["member_count"] == 2


async def test_join_is_case_insensitive(client: AsyncClient, login_as) -> None:
    """邀请码小写也能加入——家人手抄时很容易写成小写。"""
    owner_token, _ = await login_as("case-owner")
    created = await client.post("/api/v1/spaces", json={"name": "小写测试"}, headers=_auth(owner_token))
    invite_code = created.json()["data"]["invite_code"]

    member_token, _ = await login_as("case-joiner")
    response = await client.post(
        "/api/v1/spaces/join",
        json={"invite_code": invite_code.lower()},
        headers=_auth(member_token),
    )

    assert response.status_code == 200, response.text


async def test_member_cannot_see_invite_code(client: AsyncClient, login_as) -> None:
    """普通成员看不到邀请码。

    这是安全边界测试：邀请码由后端控制，不是靠前端把字段藏起来，
    所以普通成员直接调接口也只能拿到 null。
    """
    owner_token, _ = await login_as("invite-owner")
    created = await client.post("/api/v1/spaces", json={"name": "邀请码测试"}, headers=_auth(owner_token))
    space = created.json()["data"]

    member_token, _ = await login_as("invite-member")
    await client.post("/api/v1/spaces/join", json={"invite_code": space["invite_code"]}, headers=_auth(member_token))

    response = await client.get("/api/v1/spaces", headers=_auth(member_token))

    joined = next(item for item in response.json()["data"] if item["id"] == space["id"])
    assert joined["my_role"] == "member"
    assert joined["invite_code"] is None


async def test_join_twice_is_rejected(client: AsyncClient, login_as) -> None:
    """重复加入同一个家庭组要被拒绝，且提示可读。"""
    owner_token, _ = await login_as("dup-owner")
    created = await client.post("/api/v1/spaces", json={"name": "重复加入测试"}, headers=_auth(owner_token))
    invite_code = created.json()["data"]["invite_code"]

    member_token, _ = await login_as("dup-member")
    headers = _auth(member_token)
    first = await client.post("/api/v1/spaces/join", json={"invite_code": invite_code}, headers=headers)
    second = await client.post("/api/v1/spaces/join", json={"invite_code": invite_code}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 400
    assert "已经" in second.json()["message"]


async def test_join_with_invalid_code_returns_404(client: AsyncClient, login_as) -> None:
    """邀请码无效时返回 404，且不透露"是哪个环节错了"。"""
    token, _ = await login_as("bad-code")

    response = await client.post("/api/v1/spaces/join", json={"invite_code": "ZZZZZZZZ"}, headers=_auth(token))

    assert response.status_code == 404
    assert response.json()["code"] == 1004


async def test_non_member_cannot_read_space(client: AsyncClient, login_as) -> None:
    """不是家庭成员的人，读详情和成员列表都必须被拒绝。

    这条是防越权的核心：只要有人能拿到别人的 space_id（ID 是自增的，很容易猜），
    就必须保证他读不到别人家的数据。
    """
    owner_token, _ = await login_as("priv-owner")
    created = await client.post("/api/v1/spaces", json={"name": "私密家庭"}, headers=_auth(owner_token))
    space_id = created.json()["data"]["id"]

    stranger_token, _ = await login_as("stranger")
    headers = _auth(stranger_token)

    detail = await client.get(f"/api/v1/spaces/{space_id}", headers=headers)
    members = await client.get(f"/api/v1/spaces/{space_id}/members", headers=headers)

    assert detail.status_code == 403
    assert members.status_code == 403


async def test_members_list_contains_both_users(client: AsyncClient, login_as) -> None:
    """成员列表要能列出双方，并正确标出谁是创建者。"""
    owner_token, owner_id = await login_as("member-list-owner")
    created = await client.post("/api/v1/spaces", json={"name": "成员列表测试"}, headers=_auth(owner_token))
    space = created.json()["data"]

    member_token, member_id = await login_as("member-list-user")
    await client.post("/api/v1/spaces/join", json={"invite_code": space["invite_code"]}, headers=_auth(member_token))

    response = await client.get(f"/api/v1/spaces/{space['id']}/members", headers=_auth(member_token))

    assert response.status_code == 200
    members = response.json()["data"]
    by_id = {item["user_id"]: item for item in members}
    assert len(members) == 2
    assert by_id[owner_id]["role"] == "admin" and by_id[owner_id]["is_owner"] is True
    assert by_id[member_id]["role"] == "member" and by_id[member_id]["is_owner"] is False


async def test_create_space_without_token_returns_401(client: AsyncClient) -> None:
    """未登录不能创建家庭组。"""
    response = await client.post("/api/v1/spaces", json={"name": "匿名家庭"})

    assert response.status_code == 401


async def test_create_space_with_blank_name_returns_400(client: AsyncClient, login_as) -> None:
    """名称全是空格时，不能建成一个没有名字的家庭组。"""
    token, _ = await login_as("blank-name")

    response = await client.post("/api/v1/spaces", json={"name": "   "}, headers=_auth(token))

    assert response.status_code == 400
    assert "名称" in response.json()["message"]
