"""点单接口测试。

覆盖三类行为：
    1. 提交与查看：成员能提交、创建人能提交（客人借手机）、列表按时间倒序、按状态筛选；
    2. 数据正确性：菜名快照、重复菜合并份数、菜谱删除后历史单仍说得清点了什么；
    3. 权限边界（这里和菜单/冰箱**有一处刻意的不同**）：
       - 提交点单：任何成员都能做（点单是"提需求"，不是"改菜单"）；
       - 管理点单（改状态/删除）：只有**提交者本人**和**创建人**；
       - 陌生人 / 未登录：一律被拒。

关于测试数据：和别的测试一样跑在本地开发库上，每个用例用随机后缀的临时用户，可反复运行。
"""

import re

from httpx import AsyncClient

FORBIDDEN = 403

# 时间字符串结尾的时区标记，例如 "...+08:00" 或 "...Z"
TIMEZONE_SUFFIX = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")


def _auth(token: str) -> dict[str, str]:
    """构造带令牌的请求头。"""
    return {"Authorization": f"Bearer {token}"}


async def _space(client: AsyncClient, token: str, prefix: str) -> dict:
    """建一个家庭组，返回 space 数据（含 id、invite_code）。"""
    response = await client.post(
        "/api/v1/spaces", json={"name": f"点单测试-{prefix}"}, headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _member(
    client: AsyncClient,
    login_as,
    owner_token: str,
    space_id: int,
    prefix: str,
) -> tuple[str, int]:
    """造一个用邀请码加入的普通成员，返回 (令牌, 用户 ID)。"""
    listed = await client.get("/api/v1/spaces", headers=_auth(owner_token))
    assert listed.status_code == 200, listed.text
    invite_code = next(
        (item["invite_code"] for item in listed.json()["data"] if int(item["id"]) == int(space_id)),
        None,
    )
    assert invite_code, "创建人应该能看到自己的邀请码"

    token, user_id = await login_as(f"{prefix}-member")
    joined = await client.post(
        "/api/v1/spaces/join", json={"invite_code": invite_code}, headers=_auth(token)
    )
    assert joined.status_code == 200, joined.text
    return token, user_id


async def _category_id(client: AsyncClient, token: str, space_id: int) -> int:
    """取"热菜"分类的 id。家庭组创建时会自动写入默认六类。"""
    response = await client.get(f"/api/v1/spaces/{space_id}/categories", headers=_auth(token))
    assert response.status_code == 200, response.text
    for item in response.json()["data"]:
        if item["name"] == "热菜":
            return int(item["id"])
    raise AssertionError("家庭组里没有「热菜」分类")


async def _recipe(
    client: AsyncClient,
    token: str,
    space_id: int,
    name: str = "番茄炒蛋",
    **overrides,
) -> int:
    """往家庭组里加一道菜，返回菜谱 ID。

    overrides 用来覆盖辣度、售罄这类字段——**和接口的字段名保持一致**，
    不另起一套别名，免得测试里一个名字、接口里另一个名字，对不上时很难发现。
    """
    payload = {
        "name": name,
        "category_id": await _category_id(client, token, space_id),
        "description": "测试用",
    }
    payload.update(overrides)

    response = await client.post(
        f"/api/v1/spaces/{space_id}/recipes",
        json=payload,
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


async def _submit(client: AsyncClient, token: str, space_id: int, **overrides) -> dict:
    """提交一张点单，返回点单数据。

    recipe_id=... 是"只点一道菜"的简写；要传多条明细时直接用 items=... 覆盖。
    """
    payload: dict = {"guest_name": None, "remark": None}
    if "items" in overrides:
        payload["items"] = overrides.pop("items")
    else:
        payload["items"] = [{"recipe_id": overrides.pop("recipe_id"), "quantity": 1}]
    payload.update(overrides)

    response = await client.post(
        f"/api/v1/spaces/{space_id}/orders", json=payload, headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _list(client: AsyncClient, token: str, space_id: int, **params) -> list[dict]:
    """取点单列表。"""
    response = await client.get(
        f"/api/v1/spaces/{space_id}/orders", headers=_auth(token), params=params
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _can_manage(client: AsyncClient, token: str, space_id: int, order_id: int) -> bool:
    """以某个人身份去看列表，读回这张单的 can_manage。

    前端就是靠这个字段决定显示不显示"标记完成 / 删除"的，
    所以要从列表接口真实读一次，而不是直接问 Service。
    """
    for item in await _list(client, token, space_id):
        if int(item["id"]) == int(order_id):
            return bool(item["can_manage"])
    raise AssertionError(f"列表里没有点单 {order_id}")


# ==================== 提交与查看 ====================


async def test_member_can_submit_and_owner_sees_it(client: AsyncClient, login_as) -> None:
    """普通成员提交的点单，创建人能看到——这正是"客人点单、主人做饭"的主流程。"""
    owner_token, _ = await login_as("ord-owner")
    space = await _space(client, owner_token, "basic")
    space_id = int(space["id"])
    dish = await _recipe(client, owner_token, space_id)

    member_token, member_id = await _member(client, login_as, owner_token, space_id, "ord")
    order = await _submit(client, member_token, space_id, recipe_id=dish)

    assert order["status"] == "pending"
    assert order["created_by"] == member_id
    assert order["dish_count"] == 1
    assert order["total_quantity"] == 1

    # 创建人（做饭的人）看得到这张单
    listed = await _list(client, owner_token, space_id)
    assert [item["id"] for item in listed] == [order["id"]]


async def test_owner_can_submit_for_guest(client: AsyncClient, login_as) -> None:
    """客人借创建人手机点单：提交者是创建人，客人名字记在 guest_name 里。"""
    owner_token, owner_id = await login_as("ord-guest")
    space = await _space(client, owner_token, "guest")
    space_id = int(space["id"])
    dish = await _recipe(client, owner_token, space_id)

    order = await _submit(
        client,
        owner_token,
        space_id,
        recipe_id=dish,
        guest_name="  张三  ",
        remark="  少辣、不要香菜  ",
    )

    assert order["created_by"] == owner_id
    # 首尾空格要去掉，不然界面上会显示成"  张三  "
    assert order["guest_name"] == "张三"
    assert order["remark"] == "少辣、不要香菜"


async def test_order_keeps_dish_name_snapshot(client: AsyncClient, login_as) -> None:
    """点单里存的是下单那一刻的菜名快照，改菜谱名不影响已有记录。"""
    owner_token, _ = await login_as("ord-snap")
    space = await _space(client, owner_token, "snap")
    space_id = int(space["id"])
    dish = await _recipe(client, owner_token, space_id, name="番茄炒蛋")

    order = await _submit(client, owner_token, space_id, recipe_id=dish)
    assert order["items"][0]["dish_name"] == "番茄炒蛋"

    # 把菜谱改名
    renamed = await client.patch(
        f"/api/v1/spaces/{space_id}/recipes/{dish}",
        json={"name": "西红柿炒鸡蛋"},
        headers=_auth(owner_token),
    )
    assert renamed.status_code == 200, renamed.text

    listed = await _list(client, owner_token, space_id)
    assert listed[0]["items"][0]["dish_name"] == "番茄炒蛋"


async def test_duplicate_dish_is_merged(client: AsyncClient, login_as) -> None:
    """同一道菜传了两次要合并成一条，份数相加。

    前端购物车通常会自己合并，但接口是公开的，直接调接口的人可能重复传。
    """
    owner_token, _ = await login_as("ord-merge")
    space = await _space(client, owner_token, "merge")
    space_id = int(space["id"])
    dish = await _recipe(client, owner_token, space_id)

    order = await _submit(
        client,
        owner_token,
        space_id,
        items=[{"recipe_id": dish, "quantity": 2}, {"recipe_id": dish, "quantity": 3}],
    )

    assert order["dish_count"] == 1
    assert order["items"][0]["quantity"] == 5


async def test_list_is_newest_first_and_filterable(client: AsyncClient, login_as) -> None:
    """列表新的在前，并且能只看"还没做的"。"""
    owner_token, _ = await login_as("ord-list")
    space = await _space(client, owner_token, "list")
    space_id = int(space["id"])
    dish = await _recipe(client, owner_token, space_id)

    first = await _submit(client, owner_token, space_id, recipe_id=dish)
    second = await _submit(client, owner_token, space_id, recipe_id=dish)

    listed = await _list(client, owner_token, space_id)
    assert [item["id"] for item in listed] == [second["id"], first["id"]]

    # 把第一张标记完成，再看筛选
    done = await client.put(
        f"/api/v1/spaces/{space_id}/orders/{first['id']}",
        json={"status": "done"},
        headers=_auth(owner_token),
    )
    assert done.status_code == 200, done.text

    pending = await _list(client, owner_token, space_id, status="pending")
    assert [item["id"] for item in pending] == [second["id"]]

    finished = await _list(client, owner_token, space_id, status="done")
    assert [item["id"] for item in finished] == [first["id"]]


# ==================== 参数校验 ====================


async def test_rejects_empty_items(client: AsyncClient, login_as) -> None:
    """一道菜都没点要被拒。"""
    owner_token, _ = await login_as("ord-empty")
    space = await _space(client, owner_token, "empty")

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/orders",
        json={"items": []},
        headers=_auth(owner_token),
    )

    assert response.status_code == 422
    assert "至少点一道菜" in response.json()["message"]


async def test_rejects_too_many_dishes(client: AsyncClient, login_as) -> None:
    """一单最多 30 道菜。"""
    owner_token, _ = await login_as("ord-many")
    space = await _space(client, owner_token, "many")
    space_id = int(space["id"])
    dish = await _recipe(client, owner_token, space_id)

    response = await client.post(
        f"/api/v1/spaces/{space_id}/orders",
        json={"items": [{"recipe_id": dish, "quantity": 1} for _ in range(31)]},
        headers=_auth(owner_token),
    )

    assert response.status_code == 422
    assert "最多点" in response.json()["message"]


async def test_rejects_zero_and_excessive_quantity(client: AsyncClient, login_as) -> None:
    """份数必须是 1 起，且单道菜有上限。"""
    owner_token, _ = await login_as("ord-qty")
    space = await _space(client, owner_token, "qty")
    space_id = int(space["id"])
    dish = await _recipe(client, owner_token, space_id)

    zero = await client.post(
        f"/api/v1/spaces/{space_id}/orders",
        json={"items": [{"recipe_id": dish, "quantity": 0}]},
        headers=_auth(owner_token),
    )
    assert zero.status_code == 422
    assert "至少 1 份" in zero.json()["message"]

    too_many = await client.post(
        f"/api/v1/spaces/{space_id}/orders",
        json={"items": [{"recipe_id": dish, "quantity": 999}]},
        headers=_auth(owner_token),
    )
    assert too_many.status_code == 422
    assert "最多" in too_many.json()["message"]


async def test_rejects_dish_from_another_space(client: AsyncClient, login_as) -> None:
    """不能把别人家的菜点进自己家的单子。

    菜谱 ID 是自增可猜的，不校验归属就能拿自己的 space_id 配别人家的 recipe_id 越权。
    """
    token_a, _ = await login_as("ord-cross-a")
    token_b, _ = await login_as("ord-cross-b")
    space_a = await _space(client, token_a, "cross-a")
    space_b = await _space(client, token_b, "cross-b")

    dish_b = await _recipe(client, token_b, int(space_b["id"]), name="别人家的菜")

    response = await client.post(
        f"/api/v1/spaces/{space_a['id']}/orders",
        json={"items": [{"recipe_id": dish_b, "quantity": 1}]},
        headers=_auth(token_a),
    )

    assert response.status_code == 400
    assert "不在这个家庭的菜单里" in response.json()["message"]


# ==================== 权限边界 ====================


async def test_stranger_cannot_submit_or_list(client: AsyncClient, login_as) -> None:
    """陌生人（不是这个家的人）既不能提交、也不能看。"""
    owner_token, _ = await login_as("ord-stranger-owner")
    space = await _space(client, owner_token, "stranger")
    space_id = int(space["id"])
    dish = await _recipe(client, owner_token, space_id)

    stranger_token, _ = await login_as("ord-stranger")
    assert (
        await client.get(f"/api/v1/spaces/{space_id}/orders", headers=_auth(stranger_token))
    ).status_code == FORBIDDEN
    assert (
        await client.post(
            f"/api/v1/spaces/{space_id}/orders",
            json={"items": [{"recipe_id": dish, "quantity": 1}]},
            headers=_auth(stranger_token),
        )
    ).status_code == FORBIDDEN


async def test_anonymous_rejected(client: AsyncClient, login_as) -> None:
    """未登录一律 401。"""
    owner_token, _ = await login_as("ord-anon")
    space = await _space(client, owner_token, "anon")
    space_id = int(space["id"])

    assert (await client.get(f"/api/v1/spaces/{space_id}/orders")).status_code == 401
    assert (
        await client.post(f"/api/v1/spaces/{space_id}/orders", json={"items": []})
    ).status_code == 401


async def test_submitter_can_manage_own_order(client: AsyncClient, login_as) -> None:
    """提交者能把自己的单标记完成、也能删掉。

    点单是"一次性的请求"，提错了想自己撤掉是很自然的需求——
    这一点和菜单/冰箱（长期共享资料，只有创建人能改）刻意不同。
    """
    owner_token, _ = await login_as("ord-self-owner")
    space = await _space(client, owner_token, "self")
    space_id = int(space["id"])
    dish = await _recipe(client, owner_token, space_id)

    member_token, _ = await _member(client, login_as, owner_token, space_id, "self")
    order = await _submit(client, member_token, space_id, recipe_id=dish)

    done = await client.put(
        f"/api/v1/spaces/{space_id}/orders/{order['id']}",
        json={"status": "done"},
        headers=_auth(member_token),
    )
    assert done.status_code == 200, done.text
    assert done.json()["data"]["status"] == "done"

    removed = await client.delete(
        f"/api/v1/spaces/{space_id}/orders/{order['id']}", headers=_auth(member_token)
    )
    assert removed.status_code == 200, removed.text
    assert await _list(client, member_token, space_id) == []


async def test_other_member_cannot_manage_others_order(client: AsyncClient, login_as) -> None:
    """别的普通成员不能动别人的单——只有提交者本人和创建人可以。"""
    owner_token, _ = await login_as("ord-other-owner")
    space = await _space(client, owner_token, "other")
    space_id = int(space["id"])
    dish = await _recipe(client, owner_token, space_id)

    author_token, _ = await _member(client, login_as, owner_token, space_id, "other-author")
    other_token, _ = await _member(client, login_as, owner_token, space_id, "other-bystander")
    order = await _submit(client, author_token, space_id, recipe_id=dish)

    forbidden = await client.put(
        f"/api/v1/spaces/{space_id}/orders/{order['id']}",
        json={"status": "done"},
        headers=_auth(other_token),
    )
    assert forbidden.status_code == FORBIDDEN

    assert (
        await client.delete(
            f"/api/v1/spaces/{space_id}/orders/{order['id']}", headers=_auth(other_token)
        )
    ).status_code == FORBIDDEN


async def test_owner_can_manage_member_order(client: AsyncClient, login_as) -> None:
    """创建人作为家长，能管成员提交的单。"""
    owner_token, _ = await login_as("ord-boss-owner")
    space = await _space(client, owner_token, "boss")
    space_id = int(space["id"])
    dish = await _recipe(client, owner_token, space_id)

    member_token, _ = await _member(client, login_as, owner_token, space_id, "boss")
    order = await _submit(client, member_token, space_id, recipe_id=dish)

    done = await client.put(
        f"/api/v1/spaces/{space_id}/orders/{order['id']}",
        json={"status": "done"},
        headers=_auth(owner_token),
    )
    assert done.status_code == 200, done.text
    # 改单的是创建人，但响应里的"提交者"必须还是原来的成员，不能显示成创建人
    assert done.json()["data"]["created_by"] == order["created_by"]


async def test_can_manage_flag_matches_backend_rules(client: AsyncClient, login_as) -> None:
    """列表里的 can_manage 必须和真实权限完全对上。

    前端靠这个字段决定显示不显示"标记完成 / 删除"。
    它一旦和后端规则脱节，就会出现"按钮看得到、点下去被 403"——
    那是最难查的一类问题。所以把三种身份各钉一遍：
        创建人   → 成员提交的单也能管；
        提交者   → 自己的单能管；
        旁观成员 → 别人的单不能管。
    """
    owner_token, _ = await login_as("ord-flag-owner")
    space = await _space(client, owner_token, "flag")
    space_id = int(space["id"])
    dish = await _recipe(client, owner_token, space_id)

    author_token, _ = await _member(client, login_as, owner_token, space_id, "flag-author")
    bystander_token, _ = await _member(client, login_as, owner_token, space_id, "flag-bystander")
    order = await _submit(client, author_token, space_id, recipe_id=dish)

    assert await _can_manage(client, author_token, space_id, order["id"]) is True
    assert await _can_manage(client, owner_token, space_id, order["id"]) is True
    assert await _can_manage(client, bystander_token, space_id, order["id"]) is False

    # 反过来的情况：创建人自己提交的单，普通成员同样不能管
    owner_order = await _submit(client, owner_token, space_id, recipe_id=dish)
    assert await _can_manage(client, owner_token, space_id, owner_order["id"]) is True
    assert await _can_manage(client, author_token, space_id, owner_order["id"]) is False


async def test_created_at_carries_timezone(client: AsyncClient, login_as) -> None:
    """返回的时间字符串必须带时区信息。

    前端要把 created_at 转成「今天 12:30」这样给人看的时间。
    如果字符串里没有时区（例如 "2026-09-15T02:30:00"），
    JS 的 new Date() 会**按本机时区**去解析它——上午 10:30 提交的单会显示成 02:30。

    这种错很难在开发机上发现（如果本机时区恰好和服务器一致，看起来就是对的），
    所以直接把它钉在契约上：时间字符串必须自带时区。
    """
    token, _ = await login_as("ord-time")
    space = await _space(client, token, "time")
    space_id = int(space["id"])
    dish = await _recipe(client, token, space_id)

    order = await _submit(client, token, space_id, recipe_id=dish)
    assert TIMEZONE_SUFFIX.search(order["created_at"]), f"时间缺少时区信息：{order['created_at']}"

    # 列表接口的同一个字段也要一致——点单记录页显示的就是列表里的时间
    listed = await _list(client, token, space_id)
    assert TIMEZONE_SUFFIX.search(listed[0]["created_at"]), (
        f"列表里的时间缺少时区：{listed[0]['created_at']}"
    )


# ==================== 辣度（口味）====================


async def test_order_keeps_spice_snapshot(client: AsyncClient, login_as) -> None:
    """点单要存下辣度快照。

    和菜名快照是同一个道理：菜单以后改了辣度档位，
    这张历史单依然说得清当时客人要的是什么口味。
    """
    token, _ = await login_as("ord-spice-owner")
    space = await _space(client, token, "spice")
    space_id = int(space["id"])
    dish = await _recipe(
        client,
        token,
        space_id,
        name="麻婆豆腐",
        spice_options=["不辣", "微辣", "正常辣", "特辣"],
        default_spice="正常辣",
    )

    order = await _submit(
        client,
        token,
        space_id,
        items=[{"recipe_id": dish, "quantity": 2, "spice": "微辣"}],
    )

    assert order["items"][0]["dish_name"] == "麻婆豆腐"
    assert order["items"][0]["spice"] == "微辣"
    assert order["total_quantity"] == 2


async def test_same_dish_with_different_spice_stays_two_lines(
    client: AsyncClient, login_as
) -> None:
    """同一道菜选了两种辣度 → 两条明细，不能合并成一条。

    合并会把口味弄丢："两份微辣"和"一份微辣一份特辣"完全是两回事。
    """
    token, _ = await login_as("ord-spice-split")
    space = await _space(client, token, "spice-split")
    space_id = int(space["id"])
    dish = await _recipe(
        client,
        token,
        space_id,
        spice_options=["微辣", "特辣"],
        default_spice="微辣",
    )

    order = await _submit(
        client,
        token,
        space_id,
        items=[
            {"recipe_id": dish, "quantity": 1, "spice": "微辣"},
            {"recipe_id": dish, "quantity": 1, "spice": "特辣"},
        ],
    )

    assert order["dish_count"] == 2
    assert {item["spice"] for item in order["items"]} == {"微辣", "特辣"}


async def test_rejects_spice_that_dish_does_not_support(client: AsyncClient, login_as) -> None:
    """传了这道菜没有的辣度 → 被拒。

    前端已经限定了可选范围，但接口是公开的：绕过界面直接调，
    就可能存进一个菜单上根本没有的辣度，做饭的人看到会莫名其妙。
    """
    token, _ = await login_as("ord-spice-bad")
    space = await _space(client, token, "spice-bad")
    space_id = int(space["id"])
    dish = await _recipe(client, token, space_id, spice_options=["微辣"], default_spice="微辣")

    response = await client.post(
        f"/api/v1/spaces/{space_id}/orders",
        json={"items": [{"recipe_id": dish, "quantity": 1, "spice": "特辣"}]},
        headers=_auth(token),
    )

    assert response.status_code != 200
    assert "特辣" in response.text


async def test_missing_spice_falls_back_to_default(client: AsyncClient, login_as) -> None:
    """没传辣度时，落成这道菜的默认档，而不是留空。

    历史单上"这份要什么口味"必须说得清——留一片空白，
    做饭的人没法判断是"没要求"还是"没人问"。
    """
    token, _ = await login_as("ord-spice-default")
    space = await _space(client, token, "spice-default")
    space_id = int(space["id"])
    dish = await _recipe(
        client,
        token,
        space_id,
        spice_options=["微辣", "正常辣"],
        default_spice="正常辣",
    )

    order = await _submit(client, token, space_id, recipe_id=dish)

    assert order["items"][0]["spice"] == "正常辣"


async def test_dish_without_spice_records_null(client: AsyncClient, login_as) -> None:
    """本来就不问辣度的菜（汤、饮品），明细里的辣度就是空的。"""
    token, _ = await login_as("ord-spice-none")
    space = await _space(client, token, "spice-none")
    space_id = int(space["id"])
    dish = await _recipe(client, token, space_id, name="酸梅汤")

    order = await _submit(client, token, space_id, recipe_id=dish)

    assert order["items"][0]["spice"] is None


# ==================== 售罄（「今天不做」）====================


async def test_sold_out_dish_cannot_be_ordered(client: AsyncClient, login_as) -> None:
    """「今天不做」的菜不能被点单。

    前端会把加菜按钮禁掉，但那只是体验——接口这边必须真的拦住，
    否则绕过界面直接调，就会出现"今天不做"的菜出现在点单里的荒唐情况。
    """
    token, _ = await login_as("ord-soldout")
    space = await _space(client, token, "soldout")
    space_id = int(space["id"])
    dish = await _recipe(client, token, space_id, name="清蒸鲈鱼", is_sold_out=True)

    response = await client.post(
        f"/api/v1/spaces/{space_id}/orders",
        json={"items": [{"recipe_id": dish, "quantity": 1}]},
        headers=_auth(token),
    )

    assert response.status_code != 200
    assert "清蒸鲈鱼" in response.text


async def test_sold_out_dish_still_visible_in_menu(client: AsyncClient, login_as) -> None:
    """「今天不做」只是不能点，**仍然要能在菜单里看到**。

    如果直接把它从列表里藏掉，用户会以为这道菜被删了。
    """
    token, _ = await login_as("ord-soldout-visible")
    space = await _space(client, token, "soldout-visible")
    space_id = int(space["id"])
    dish = await _recipe(client, token, space_id, name="红烧肉", is_sold_out=True)

    response = await client.get(f"/api/v1/spaces/{space_id}/recipes", headers=_auth(token))
    assert response.status_code == 200, response.text

    names = [item["name"] for item in response.json()["data"]["recipes"]]
    assert "红烧肉" in names
    listed = next(item for item in response.json()["data"]["recipes"] if item["id"] == dish)
    assert listed["is_sold_out"] is True


async def test_cross_space_order_is_not_found(client: AsyncClient, login_as) -> None:
    """拿自己家的路由去动别人家的点单 → 404（不区分"不存在"和"不是你的"）。"""
    token_a, _ = await login_as("ord-404-a")
    token_b, _ = await login_as("ord-404-b")
    space_a = await _space(client, token_a, "404-a")
    space_b = await _space(client, token_b, "404-b")

    dish_b = await _recipe(client, token_b, int(space_b["id"]))
    order_b = await _submit(client, token_b, int(space_b["id"]), recipe_id=dish_b)

    response = await client.put(
        f"/api/v1/spaces/{space_a['id']}/orders/{order_b['id']}",
        json={"status": "done"},
        headers=_auth(token_a),
    )
    assert response.status_code == 404


async def test_deleting_recipe_keeps_order_readable(client: AsyncClient, login_as) -> None:
    """删掉菜谱之后，历史点单仍然说得清当时点了什么。

    这是 dish_name 快照存在的意义：
    如果只存 recipe_id 且用 CASCADE，删菜谱会把历史点单悄悄改短。
    """
    owner_token, _ = await login_as("ord-del-recipe")
    space = await _space(client, owner_token, "del-recipe")
    space_id = int(space["id"])
    dish = await _recipe(client, owner_token, space_id, name="红烧肉")

    order = await _submit(client, owner_token, space_id, recipe_id=dish)

    deleted = await client.delete(
        f"/api/v1/spaces/{space_id}/recipes/{dish}", headers=_auth(owner_token)
    )
    assert deleted.status_code == 200, deleted.text

    listed = await _list(client, owner_token, space_id)
    assert len(listed) == 1
    assert listed[0]["id"] == order["id"]
    item = listed[0]["items"][0]
    assert item["dish_name"] == "红烧肉"  # 菜名还在
    assert item["recipe_id"] is None  # 但指向菜谱的引用已置空
