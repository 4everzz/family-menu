"""家庭组成员管理测试：退出 / 移除 / 解散。

覆盖五类行为：
    1. 退出：普通成员能退出；退出后列表里不再有这个家、也读不到它的数据；
    2. 创建人保护：创建人不能直接退出（要解散），也不能移除自己；
    3. 移除：只有创建人能移除别人；移除后对方立刻失去访问权；
    4. 解散：只有创建人能解散；解散后整个家庭连同菜谱、分类一起消失；
    5. 权限边界：非成员 403、未登录 401。

关于测试数据：和家庭组测试一样跑在本地开发库上，
每个用例用随机后缀的临时用户，所以可以反复运行而不会互相干扰。
"""

from httpx import AsyncClient


def _auth(token: str) -> dict[str, str]:
    """构造带令牌的请求头。"""
    return {"Authorization": f"Bearer {token}"}


async def _create_space(client: AsyncClient, token: str, name: str = "成员测试家") -> dict:
    """建一个家庭组，返回创建者视角的信息（含邀请码）。"""
    response = await client.post("/api/v1/spaces", json={"name": name}, headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _join_space(client: AsyncClient, token: str, invite_code: str) -> dict:
    """用邀请码加入家庭组。"""
    response = await client.post(
        "/api/v1/spaces/join",
        json={"invite_code": invite_code},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _add_recipe(client: AsyncClient, token: str, space_id: int) -> dict:
    """往家庭组里加一道菜（用来验证解散时的级联删除确实生效）。"""
    cats = await client.get(f"/api/v1/spaces/{space_id}/categories", headers=_auth(token))
    category_id = cats.json()["data"][0]["id"]
    response = await client.post(
        f"/api/v1/spaces/{space_id}/recipes",
        json={"name": "红烧肉", "category_id": category_id},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ==================== 退出家庭组 ====================


async def test_member_can_leave_space(client: AsyncClient, login_as) -> None:
    """普通成员可以退出。退出后，他和这个家就没关系了。"""
    owner_token, _ = await login_as("leave-owner")
    space = await _create_space(client, owner_token)

    member_token, member_id = await login_as("leave-member")
    await _join_space(client, member_token, space["invite_code"])

    left = await client.post(f"/api/v1/spaces/{space['id']}/leave", headers=_auth(member_token))
    assert left.status_code == 200, left.text

    # 自己的家庭组列表里不再有这个家
    mine = await client.get("/api/v1/spaces", headers=_auth(member_token))
    assert space["id"] not in [item["id"] for item in mine.json()["data"]]

    # 创建人看到的成员列表里也少了一个人
    members = await client.get(f"/api/v1/spaces/{space['id']}/members", headers=_auth(owner_token))
    assert member_id not in [item["user_id"] for item in members.json()["data"]]


async def test_after_leaving_cannot_read_space_data(client: AsyncClient, login_as) -> None:
    """退出之后就读不到这个家的任何数据了。"""
    owner_token, _ = await login_as("leave2-owner")
    space = await _create_space(client, owner_token)
    await _add_recipe(client, owner_token, space["id"])

    member_token, _ = await login_as("leave2-member")
    await _join_space(client, member_token, space["invite_code"])
    await client.post(f"/api/v1/spaces/{space['id']}/leave", headers=_auth(member_token))

    recipes = await client.get(f"/api/v1/spaces/{space['id']}/recipes", headers=_auth(member_token))
    members = await client.get(f"/api/v1/spaces/{space['id']}/members", headers=_auth(member_token))

    assert recipes.status_code == 403
    assert members.status_code == 403


async def test_owner_cannot_leave(client: AsyncClient, login_as) -> None:
    """创建人不能直接退出，必须走「解散」这条路。"""
    owner_token, _ = await login_as("leave-owner-block")
    space = await _create_space(client, owner_token)

    response = await client.post(f"/api/v1/spaces/{space['id']}/leave", headers=_auth(owner_token))

    assert response.status_code == 400, response.text
    assert "创建人" in response.json()["message"]


async def test_non_member_cannot_leave(client: AsyncClient, login_as) -> None:
    """不是这个家的人，谈不上"退出"。"""
    owner_token, _ = await login_as("leave-nonmember-owner")
    space = await _create_space(client, owner_token)

    stranger_token, _ = await login_as("leave-nonmember")
    response = await client.post(
        f"/api/v1/spaces/{space['id']}/leave", headers=_auth(stranger_token)
    )

    assert response.status_code == 403


# ==================== 移除成员 ====================


async def test_owner_can_remove_member(client: AsyncClient, login_as) -> None:
    """创建人能把成员移出去，而且对方会立刻失去访问权。"""
    owner_token, _ = await login_as("remove-owner")
    space = await _create_space(client, owner_token)

    member_token, member_id = await login_as("remove-member")
    await _join_space(client, member_token, space["invite_code"])

    response = await client.delete(
        f"/api/v1/spaces/{space['id']}/members/{member_id}",
        headers=_auth(owner_token),
    )
    assert response.status_code == 200, response.text

    members = await client.get(f"/api/v1/spaces/{space['id']}/members", headers=_auth(owner_token))
    assert member_id not in [item["user_id"] for item in members.json()["data"]]

    blocked = await client.get(
        f"/api/v1/spaces/{space['id']}/recipes", headers=_auth(member_token)
    )
    assert blocked.status_code == 403


async def test_member_cannot_remove_others(client: AsyncClient, login_as) -> None:
    """普通成员没有移除别人的权限。"""
    owner_token, _ = await login_as("remove-priv-owner")
    space = await _create_space(client, owner_token)

    first_token, _ = await login_as("remove-priv-first")
    await _join_space(client, first_token, space["invite_code"])

    second_token, second_id = await login_as("remove-priv-second")
    await _join_space(client, second_token, space["invite_code"])

    response = await client.delete(
        f"/api/v1/spaces/{space['id']}/members/{second_id}",
        headers=_auth(first_token),
    )

    assert response.status_code == 403


async def test_owner_cannot_remove_self(client: AsyncClient, login_as) -> None:
    """创建人不能移除自己，否则会留下一个没有创建人的家。"""
    owner_token, owner_id = await login_as("remove-self-owner")
    space = await _create_space(client, owner_token)

    response = await client.delete(
        f"/api/v1/spaces/{space['id']}/members/{owner_id}",
        headers=_auth(owner_token),
    )

    assert response.status_code == 400, response.text


async def test_remove_unknown_member_returns_404(client: AsyncClient, login_as) -> None:
    """移除一个不在组里的人，报「不在该家庭组里」。"""
    owner_token, _ = await login_as("remove-unknown-owner")
    space = await _create_space(client, owner_token)

    _stranger_token, stranger_id = await login_as("remove-unknown-stranger")

    response = await client.delete(
        f"/api/v1/spaces/{space['id']}/members/{stranger_id}",
        headers=_auth(owner_token),
    )

    assert response.status_code == 404, response.text


# ==================== 解散家庭组 ====================


async def test_owner_can_dissolve_space(client: AsyncClient, login_as) -> None:
    """创建人解散家庭组：所有人的列表里都不再有这个家。"""
    owner_token, _ = await login_as("dissolve-owner")
    space = await _create_space(client, owner_token)
    await _add_recipe(client, owner_token, space["id"])

    member_token, _ = await login_as("dissolve-member")
    await _join_space(client, member_token, space["invite_code"])

    response = await client.delete(f"/api/v1/spaces/{space['id']}", headers=_auth(owner_token))
    assert response.status_code == 200, response.text

    mine = await client.get("/api/v1/spaces", headers=_auth(owner_token))
    assert space["id"] not in [item["id"] for item in mine.json()["data"]]

    member_mine = await client.get("/api/v1/spaces", headers=_auth(member_token))
    assert space["id"] not in [item["id"] for item in member_mine.json()["data"]]


async def test_member_cannot_dissolve_space(client: AsyncClient, login_as) -> None:
    """普通成员不能解散家庭组。"""
    owner_token, _ = await login_as("dissolve-priv-owner")
    space = await _create_space(client, owner_token)

    member_token, _ = await login_as("dissolve-priv-member")
    await _join_space(client, member_token, space["invite_code"])

    response = await client.delete(f"/api/v1/spaces/{space['id']}", headers=_auth(member_token))
    assert response.status_code == 403

    # 这个家必须还在
    still_there = await client.get(f"/api/v1/spaces/{space['id']}", headers=_auth(owner_token))
    assert still_there.status_code == 200


async def test_dissolved_space_data_is_gone(client: AsyncClient, login_as) -> None:
    """解散之后，用原来的家庭组 ID 读详情、菜谱、分类，全都应该 404。"""
    owner_token, _ = await login_as("dissolve-gone-owner")
    space = await _create_space(client, owner_token)
    await _add_recipe(client, owner_token, space["id"])

    await client.delete(f"/api/v1/spaces/{space['id']}", headers=_auth(owner_token))

    detail = await client.get(f"/api/v1/spaces/{space['id']}", headers=_auth(owner_token))
    recipes = await client.get(f"/api/v1/spaces/{space['id']}/recipes", headers=_auth(owner_token))
    categories = await client.get(
        f"/api/v1/spaces/{space['id']}/categories", headers=_auth(owner_token)
    )

    assert detail.status_code == 404
    assert recipes.status_code == 404
    assert categories.status_code == 404


# ==================== 登录态 ====================


async def test_member_management_requires_login(client: AsyncClient, login_as) -> None:
    """退出、移除、解散三个接口都必须登录才能用。"""
    owner_token, owner_id = await login_as("mgmt-anonymous-owner")
    space = await _create_space(client, owner_token)

    left = await client.post(f"/api/v1/spaces/{space['id']}/leave")
    removed = await client.delete(f"/api/v1/spaces/{space['id']}/members/{owner_id}")
    dissolved = await client.delete(f"/api/v1/spaces/{space['id']}")

    assert left.status_code == 401
    assert removed.status_code == 401
    assert dissolved.status_code == 401
