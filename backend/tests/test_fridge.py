"""家庭冰箱接口测试。

覆盖的行为：
    1. 列表 / 新增 / 部分修改 / 删除；
    2. 顶部"临期件数"统计（含已过期 + 7 天内，不含无保质期和无临期的）；
    3. 筛选：按分类、存放、关键词；
    4. 权限边界（和菜单同一套口径——仅创建人可改）：
       - 普通成员：新增/修改/删除一律 403，但**读**正常；
       - 陌生人 / 未登录：读和写都被拒；
       - 跨家庭组：拿 A 家的路由访问 B 家的食材 → 404（防越权）。

关于测试数据：跑在本地开发库上，每个用例用随机后缀的临时用户，可反复运行。
"""

from datetime import date, timedelta

from httpx import AsyncClient


FORBIDDEN = 403


def _auth(token: str) -> dict[str, str]:
    """构造带令牌的请求头。"""
    return {"Authorization": f"Bearer {token}"}


async def _login(client: AsyncClient, login_as, prefix: str) -> str:
    """造一个临时用户，返回令牌。"""
    token, _ = await login_as(prefix)
    return token


async def _space(client: AsyncClient, token: str, prefix: str) -> dict:
    """建一个家庭组，返回 space 数据（含 id、invite_code）。"""
    response = await client.post(
        "/api/v1/spaces", json={"name": f"冰箱测试-{prefix}"}, headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _member(client: AsyncClient, login_as, owner_token: str, space_id: int, prefix: str) -> str:
    """造一个用邀请码加入的普通成员，返回其令牌。"""
    listed = await client.get("/api/v1/spaces", headers=_auth(owner_token))
    assert listed.status_code == 200, listed.text
    invite_code = next(
        (item["invite_code"] for item in listed.json()["data"] if int(item["id"]) == int(space_id)),
        None,
    )
    assert invite_code, "创建人应该能看到自己的邀请码"

    token = await _login(client, login_as, f"{prefix}-member")
    joined = await client.post(
        "/api/v1/spaces/join", json={"invite_code": invite_code}, headers=_auth(token)
    )
    assert joined.status_code == 200, joined.text
    return token


def _payload(**overrides) -> dict:
    """一条食材的默认新增参数，调用方可覆盖。"""
    data = {
        "name": "鸡蛋",
        "quantity": 10,
        "unit": "个",
        "category": "肉蛋",
        "storage": "冷藏",
        "expiry_date": None,
        "note": "",
    }
    data.update(overrides)
    return data


async def _add(client: AsyncClient, token: str, space_id: int, **overrides) -> dict:
    """新增食材，返回响应体 data。"""
    response = await client.post(
        f"/api/v1/spaces/{space_id}/fridge", json=_payload(**overrides), headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _list(client: AsyncClient, token: str, space_id: int, **params) -> dict:
    """读冰箱列表，返回响应体 data（含 items、expiring_count）。"""
    response = await client.get(f"/api/v1/spaces/{space_id}/fridge", params=params, headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ==================== 基本读写 ====================


async def test_create_and_list(client: AsyncClient, login_as) -> None:
    """新增后列表能看到，且字段回传正确。"""
    token = await _login(client, login_as, "fridge-basic")
    space = await _space(client, token, "fridge-basic")

    item = await _add(client, token, space["id"], name="牛奶", quantity=2, unit="盒", category="饮品")
    assert item["name"] == "牛奶"
    assert item["quantity"] == 2
    assert item["created_by_nickname"]

    data = await _list(client, token, space["id"])
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == item["id"]


async def test_partial_update_and_delete(client: AsyncClient, login_as) -> None:
    """部分修改只改传来的字段；删除后列表变空。"""
    token = await _login(client, login_as, "fridge-crud")
    space = await _space(client, token, "fridge-crud")

    item = await _add(client, token, space["id"], name="西红柿", quantity=5, unit="个")

    # 只改数量，名字不动
    updated = await client.put(
        f"/api/v1/spaces/{space['id']}/fridge/{item['id']}",
        json={"quantity": 8},
        headers=_auth(token),
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()["data"]
    assert body["quantity"] == 8
    assert body["name"] == "西红柿"  # 没传，保持原值

    # 显式把单位清空（传 null）
    cleared = await client.put(
        f"/api/v1/spaces/{space['id']}/fridge/{item['id']}",
        json={"unit": None},
        headers=_auth(token),
    )
    assert cleared.json()["data"]["unit"] is None

    deleted = await client.delete(
        f"/api/v1/spaces/{space['id']}/fridge/{item['id']}", headers=_auth(token)
    )
    assert deleted.status_code == 200, deleted.text
    assert (await _list(client, token, space["id"]))["items"] == []


# ==================== 临期统计 ====================


async def test_expiring_count(client: AsyncClient, login_as) -> None:
    """临期件数只统计"有保质期且落在窗口内"的，无保质期的和不临期的都不算。"""
    token = await _login(client, login_as, "fridge-exp")
    space = await _space(client, token, "fridge-exp")

    # 3 天后过期 → 算临期
    await _add(client, token, space["id"], name="酸奶", expiry_date=str(date.today() + timedelta(days=3)))
    # 已过期 → 也算（更该处理）
    await _add(client, token, space["id"], name="剩菜", expiry_date=str(date.today() - timedelta(days=1)))
    # 30 天后才过期 → 不算
    await _add(client, token, space["id"], name="大米", expiry_date=str(date.today() + timedelta(days=30)))
    # 没填保质期 → 不算
    await _add(client, token, space["id"], name="盐", expiry_date=None)

    data = await _list(client, token, space["id"])
    assert data["expiring_count"] == 2


# ==================== 筛选 ====================


async def test_filters(client: AsyncClient, login_as) -> None:
    """按分类、存放、关键词筛选都能正确缩小结果。"""
    token = await _login(client, login_as, "fridge-filter")
    space = await _space(client, token, "fridge-filter")

    await _add(client, token, space["id"], name="鸡蛋", category="肉蛋", storage="冷藏")
    await _add(client, token, space["id"], name="白菜", category="蔬菜", storage="冷藏")
    await _add(client, token, space["id"], name="冻虾", category="水产", storage="冷冻", note="已解冻一半")

    by_cat = await _list(client, token, space["id"], category="肉蛋")
    assert len(by_cat["items"]) == 1 and by_cat["items"][0]["name"] == "鸡蛋"

    by_storage = await _list(client, token, space["id"], storage="冷冻")
    assert len(by_storage["items"]) == 1 and by_storage["items"][0]["name"] == "冻虾"

    by_keyword = await _list(client, token, space["id"], keyword="解冻")
    assert len(by_keyword["items"]) == 1 and by_keyword["items"][0]["name"] == "冻虾"


# ==================== 权限边界 ====================


async def test_member_read_ok_but_write_forbidden(client: AsyncClient, login_as) -> None:
    """仅创建人可改：普通成员能读冰箱，但增删改一律 403。"""
    owner = await _login(client, login_as, "fridge-perm")
    space = await _space(client, owner, "fridge-perm")
    item = await _add(client, owner, space["id"], name="豆腐")

    member = await _member(client, login_as, owner, space["id"], "fridge-perm")

    # 读：普通成员正常
    assert (await _list(client, member, space["id"]))["items"]

    # 写：普通成员一律被拒
    assert (
        await client.post(f"/api/v1/spaces/{space['id']}/fridge", json=_payload(name="偷加"), headers=_auth(member))
    ).status_code == FORBIDDEN
    assert (
        await client.put(f"/api/v1/spaces/{space['id']}/fridge/{item['id']}", json={"quantity": 1}, headers=_auth(member))
    ).status_code == FORBIDDEN
    assert (
        await client.delete(f"/api/v1/spaces/{space['id']}/fridge/{item['id']}", headers=_auth(member))
    ).status_code == FORBIDDEN


async def test_owner_can_write(client: AsyncClient, login_as) -> None:
    """创建人自己写一切正常（不能把自己也拦了）。"""
    owner = await _login(client, login_as, "fridge-owner")
    space = await _space(client, owner, "fridge-owner")
    item = await _add(client, owner, space["id"], name="排骨")

    put = await client.put(
        f"/api/v1/spaces/{space['id']}/fridge/{item['id']}",
        json={"quantity": 3, "note": "周六炖"},
        headers=_auth(owner),
    )
    assert put.status_code == 200, put.text
    assert put.json()["data"]["note"] == "周六炖"


async def test_stranger_and_anonymous_forbidden(client: AsyncClient, login_as) -> None:
    """陌生人（非成员）和未登录访问冰箱一律被拒。"""
    owner = await _login(client, login_as, "fridge-stranger")
    space = await _space(client, owner, "fridge-stranger")
    item = await _add(client, owner, space["id"], name="鱼")

    outsider = await _login(client, login_as, "fridge-outsider")
    assert (
        await client.get(f"/api/v1/spaces/{space['id']}/fridge", headers=_auth(outsider))
    ).status_code == FORBIDDEN

    # 未登录
    assert (await client.get(f"/api/v1/spaces/{space['id']}/fridge")).status_code == 401
    assert (
        await client.post(f"/api/v1/spaces/{space['id']}/fridge", json=_payload(name="x"))
    ).status_code == 401


async def test_cross_space_item_is_not_visible(client: AsyncClient, login_as) -> None:
    """跨家庭组防越权：用 A 家的路由访问 B 家的食材 ID，必须 404。

    创建人即便在别处也是创建人，也不能借 A 的路由改到 B 的食材——
    服务会先确认"这条食材属于这个 space_id"，不属于就当不存在。
    """
    owner_a = await _login(client, login_as, "fridge-x-a")
    space_a = await _space(client, owner_a, "fridge-x-a")
    item_a = await _add(client, owner_a, space_a["id"], name="A家的鸡蛋")

    owner_b = await _login(client, login_as, "fridge-x-b")
    space_b = await _space(client, owner_b, "fridge-x-b")
    await _add(client, owner_b, space_b["id"], name="B家的肉")

    # 用 A 的路由去读 B 家的食材 id → 404（不是 403，因为它压根不属于 A）
    assert (
        await client.get(f"/api/v1/spaces/{space_a['id']}/fridge/{item_a['id']}", headers=_auth(owner_b))
    ).status_code == FORBIDDEN  # owner_b 本就不是 A 的成员，成员校验先兜住
    # 真正跨空间：member of A 拿 B 的 item id 走 A 路由 → 404
    member_a = await _member(client, login_as, owner_a, space_a["id"], "fridge-x-a")
    # 给 member_a 一个 B 家的 item：先让 owner_b 把 item id 暴露出来
    b_items = await client.get(f"/api/v1/spaces/{space_b['id']}/fridge", headers=_auth(owner_b))
    b_item_id = b_items.json()["data"]["items"][0]["id"]
    assert (
        await client.get(f"/api/v1/spaces/{space_a['id']}/fridge/{b_item_id}", headers=_auth(member_a))
    ).status_code == 404
