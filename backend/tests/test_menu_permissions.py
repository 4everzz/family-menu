"""菜单权限测试：只有创建人能改菜单。

背景（为什么单独开一个文件）：
    早期版本允许**任何家庭成员**增删改菜谱和分类，后来按用户要求收紧为
    **创建人专属**（创建人的三项专属权力：改菜单、解散家庭组、移除成员）。
    这个文件专门守住这条线——它是一条产品规则，一旦被改坏，
    表现就是"普通成员把家里的菜删了"，而且是**不可逆**的破坏。

覆盖五类行为：
    1. 普通成员：新增/修改/删除菜谱一律 403；
    2. 普通成员：新增/改名/删除分类一律 403；
    3. 普通成员：**读**列表和详情仍然正常（收紧的是写，不是读）；
    4. 创建人：同样的写操作一切正常（不能收紧到把自己也拦了）；
    5. 陌生人 / 未登录：依然被拒（加了创建人判断，不能把成员校验放宽）。

关于测试数据：和其余测试一样跑在本地开发库上，
每个用例用随机后缀的临时用户，可以反复运行而互不干扰。
"""

from httpx import AsyncClient

FORBIDDEN = 403


def _auth(token: str) -> dict[str, str]:
    """构造带令牌的请求头。"""
    return {"Authorization": f"Bearer {token}"}


async def _owner(client: AsyncClient, login_as, prefix: str) -> tuple[str, dict]:
    """造一个"建了家庭组的人"，返回 (令牌, 家庭组)。"""
    token, _ = await login_as(f"{prefix}-owner")
    response = await client.post(
        "/api/v1/spaces", json={"name": f"权限测试-{prefix}"}, headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    return token, response.json()["data"]


async def _member(client: AsyncClient, login_as, owner_token: str, space_id: int, prefix: str) -> str:
    """造一个"用邀请码加入的普通成员"，返回其令牌。

    邀请码只有创建人能看到，所以这里用创建人的令牌去列表里取。
    """
    listed = await client.get("/api/v1/spaces", headers=_auth(owner_token))
    assert listed.status_code == 200, listed.text
    invite_code = next(
        (item["invite_code"] for item in listed.json()["data"] if int(item["id"]) == int(space_id)),
        None,
    )
    assert invite_code, "创建人应该能看到自己的邀请码"

    token, _ = await login_as(f"{prefix}-member")
    joined = await client.post(
        "/api/v1/spaces/join", json={"invite_code": invite_code}, headers=_auth(token)
    )
    assert joined.status_code == 200, joined.text
    return token


async def _category_id(client: AsyncClient, token: str, space_id: int, name: str) -> int:
    """按名字取分类 id。"""
    response = await client.get(f"/api/v1/spaces/{space_id}/categories", headers=_auth(token))
    assert response.status_code == 200, response.text
    for item in response.json()["data"]:
        if item["name"] == name:
            return int(item["id"])
    raise AssertionError(f"家庭组 {space_id} 里没有找到分类「{name}」")


async def _create_recipe(
    client: AsyncClient, token: str, space_id: int, category_id: int, name: str = "红烧肉"
) -> dict:
    """加一道菜（调用方通常传创建人的令牌，所以这里断言成功）。"""
    response = await client.post(
        f"/api/v1/spaces/{space_id}/recipes",
        json={"name": name, "category_id": category_id},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ==================== 普通成员：不能改菜谱 ====================


async def test_member_cannot_create_recipe(client: AsyncClient, login_as) -> None:
    """普通成员新增菜谱要被拒绝，并给出可读原因。"""
    owner_token, space = await _owner(client, login_as, "member-create")
    member_token = await _member(client, login_as, owner_token, space["id"], "member-create")
    hot = await _category_id(client, owner_token, space["id"], "热菜")

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes",
        json={"name": "普通成员偷偷加的菜", "category_id": hot},
        headers=_auth(member_token),
    )

    assert response.status_code == FORBIDDEN, response.text
    assert "创建人" in response.json()["message"]


async def test_member_cannot_update_recipe(client: AsyncClient, login_as) -> None:
    """普通成员改菜谱（含改分类、改简介）要被拒绝。"""
    owner_token, space = await _owner(client, login_as, "member-update")
    member_token = await _member(client, login_as, owner_token, space["id"], "member-update")
    hot = await _category_id(client, owner_token, space["id"], "热菜")
    recipe = await _create_recipe(client, owner_token, space["id"], hot, "原始菜名")

    # PATCH 与 POST（小程序入口）两条路由都要拦，它们指向同一份代码
    patched = await client.patch(
        f"/api/v1/spaces/{space['id']}/recipes/{recipe['id']}",
        json={"name": "被改掉的名字"},
        headers=_auth(member_token),
    )
    posted = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes/{recipe['id']}",
        json={"description": "被改掉的简介"},
        headers=_auth(member_token),
    )

    assert patched.status_code == FORBIDDEN, patched.text
    assert posted.status_code == FORBIDDEN, posted.text

    # 关键：确认数据真的没被改动，而不是"返回 403 但其实改了"
    detail = await client.get(
        f"/api/v1/spaces/{space['id']}/recipes/{recipe['id']}", headers=_auth(owner_token)
    )
    assert detail.json()["data"]["name"] == "原始菜名"


async def test_member_cannot_delete_recipe(client: AsyncClient, login_as) -> None:
    """普通成员删菜谱要被拒绝，且菜还在。"""
    owner_token, space = await _owner(client, login_as, "member-delete")
    member_token = await _member(client, login_as, owner_token, space["id"], "member-delete")
    hot = await _category_id(client, owner_token, space["id"], "热菜")
    recipe = await _create_recipe(client, owner_token, space["id"], hot, "不能被删的菜")

    response = await client.delete(
        f"/api/v1/spaces/{space['id']}/recipes/{recipe['id']}", headers=_auth(member_token)
    )

    assert response.status_code == FORBIDDEN, response.text
    still_there = await client.get(
        f"/api/v1/spaces/{space['id']}/recipes/{recipe['id']}", headers=_auth(owner_token)
    )
    assert still_there.status_code == 200, still_there.text


# ==================== 普通成员：不能改分类 ====================


async def test_member_cannot_create_category(client: AsyncClient, login_as) -> None:
    """普通成员新增分类要被拒绝。"""
    owner_token, space = await _owner(client, login_as, "member-cat-create")
    member_token = await _member(client, login_as, owner_token, space["id"], "member-cat-create")

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/categories",
        json={"name": "普通成员加的夜宵"},
        headers=_auth(member_token),
    )

    assert response.status_code == FORBIDDEN, response.text


async def test_member_cannot_rename_category(client: AsyncClient, login_as) -> None:
    """普通成员给分类改名要被拒绝，且名字没变。

    改名虽然"看起来无害"，但它影响全家——所有挂在这个分类下的菜
    显示出来的分类名都会跟着变，属于典型的菜单管理动作。
    """
    owner_token, space = await _owner(client, login_as, "member-cat-rename")
    member_token = await _member(client, login_as, owner_token, space["id"], "member-cat-rename")
    hot = await _category_id(client, owner_token, space["id"], "热菜")

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/categories/{hot}",
        json={"name": "被改掉的热菜"},
        headers=_auth(member_token),
    )

    assert response.status_code == FORBIDDEN, response.text
    assert await _category_id(client, owner_token, space["id"], "热菜") == hot


async def test_member_cannot_delete_category(client: AsyncClient, login_as) -> None:
    """普通成员删分类要被拒绝（这里用的是空分类，避免被"还有菜"的规则挡住而误判）。"""
    owner_token, space = await _owner(client, login_as, "member-cat-delete")
    member_token = await _member(client, login_as, owner_token, space["id"], "member-cat-delete")

    created = await client.post(
        f"/api/v1/spaces/{space['id']}/categories",
        json={"name": "临时分类"},
        headers=_auth(owner_token),
    )
    assert created.status_code == 200, created.text
    empty_category = int(created.json()["data"]["id"])

    response = await client.delete(
        f"/api/v1/spaces/{space['id']}/categories/{empty_category}", headers=_auth(member_token)
    )

    assert response.status_code == FORBIDDEN, response.text


# ==================== 收紧的是写，不是读 ====================


async def test_member_can_still_read_menu(client: AsyncClient, login_as) -> None:
    """普通成员浏览菜单必须照常可用——否则"家人能看到菜谱"这件事就不成立了。"""
    owner_token, space = await _owner(client, login_as, "member-read")
    member_token = await _member(client, login_as, owner_token, space["id"], "member-read")
    hot = await _category_id(client, owner_token, space["id"], "热菜")
    recipe = await _create_recipe(client, owner_token, space["id"], hot, "家人能看到的菜")

    listing = await client.get(
        f"/api/v1/spaces/{space['id']}/recipes", headers=_auth(member_token)
    )
    detail = await client.get(
        f"/api/v1/spaces/{space['id']}/recipes/{recipe['id']}", headers=_auth(member_token)
    )
    categories = await client.get(
        f"/api/v1/spaces/{space['id']}/categories", headers=_auth(member_token)
    )

    assert listing.status_code == 200, listing.text
    assert detail.status_code == 200, detail.text
    assert categories.status_code == 200, categories.text
    assert [item["name"] for item in listing.json()["data"]["recipes"]] == ["家人能看到的菜"]


# ==================== 创建人自己不受影响 ====================


async def test_owner_can_manage_menu(client: AsyncClient, login_as) -> None:
    """创建人的完整增删改链路必须全部正常——收紧不能紧到自己头上。"""
    token, space = await _owner(client, login_as, "owner-full")

    hot = await _category_id(client, token, space["id"], "热菜")
    created = await _create_recipe(client, token, space["id"], hot, "创建人加的菜")

    renamed = await client.post(
        f"/api/v1/spaces/{space['id']}/categories/{hot}",
        json={"name": "家常热菜"},
        headers=_auth(token),
    )
    assert renamed.status_code == 200, renamed.text

    updated = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes/{created['id']}",
        json={"description": "改成简介也没问题"},
        headers=_auth(token),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["description"] == "改成简介也没问题"

    deleted = await client.delete(
        f"/api/v1/spaces/{space['id']}/recipes/{created['id']}", headers=_auth(token)
    )
    assert deleted.status_code == 200, deleted.text


# ==================== 陌生人 / 未登录 ====================


async def test_outsider_cannot_write_menu(client: AsyncClient, login_as) -> None:
    """完全不相干的人既不能读也不能写——加了创建人判断，不能把成员校验放宽。"""
    owner_token, space = await _owner(client, login_as, "outsider")
    hot = await _category_id(client, owner_token, space["id"], "热菜")
    recipe = await _create_recipe(client, owner_token, space["id"], hot)

    outsider_token, _ = await login_as("outsider-stranger")

    created = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes",
        json={"name": "外人加的菜", "category_id": hot},
        headers=_auth(outsider_token),
    )
    deleted = await client.delete(
        f"/api/v1/spaces/{space['id']}/recipes/{recipe['id']}", headers=_auth(outsider_token)
    )
    renamed = await client.post(
        f"/api/v1/spaces/{space['id']}/categories/{hot}",
        json={"name": "外人改的名"},
        headers=_auth(outsider_token),
    )

    assert created.status_code == FORBIDDEN, created.text
    assert deleted.status_code == FORBIDDEN, deleted.text
    assert renamed.status_code == FORBIDDEN, renamed.text


async def test_menu_write_requires_login(client: AsyncClient, login_as) -> None:
    """不带令牌写菜单返回 401（是 401 不是 405，说明路由确实存在）。"""
    owner_token, space = await _owner(client, login_as, "anon-write")
    hot = await _category_id(client, owner_token, space["id"], "热菜")
    recipe = await _create_recipe(client, owner_token, space["id"], hot)

    created = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes", json={"name": "匿名加的菜", "category_id": hot}
    )
    updated = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes/{recipe['id']}", json={"name": "匿名改的名"}
    )
    deleted = await client.delete(f"/api/v1/spaces/{space['id']}/recipes/{recipe['id']}")
    category = await client.post(
        f"/api/v1/spaces/{space['id']}/categories", json={"name": "匿名加的分类"}
    )

    assert created.status_code == 401
    assert updated.status_code == 401
    assert deleted.status_code == 401
    assert category.status_code == 401
