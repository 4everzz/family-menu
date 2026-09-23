"""家庭菜谱分类接口测试。

覆盖五类行为：
    1. 默认分类：新建家庭组自动带 6 个分类，顺序和名字都固定；
    2. 增删改：新增排在最后、改名生效、删除空分类成功；
    3. 删除保护：分类下还有菜时拒绝删除，并告诉用户有几道菜；
    4. 重名拦截：同一个家里不允许两个同名分类，新增和改名两条路径都要拦；
    5. 权限边界：非成员一律拒绝、跨家庭组猜分类 ID 读不到、未登录 401。

关于测试数据：和家庭组测试一样直接跑在本地开发库上，
每个用例用随机后缀的临时用户，所以可以反复运行而不会互相干扰。
"""

from httpx import AsyncClient

# 默认分类的名字与顺序是后端定的契约，这里写死是为了"哪天有人改了默认值"能立刻被发现
EXPECTED_DEFAULT_CATEGORIES = ["凉菜", "热菜", "汤羹", "主食", "甜点", "饮品"]


def _auth(token: str) -> dict[str, str]:
    """构造带令牌的请求头。"""
    return {"Authorization": f"Bearer {token}"}


async def _create_space(client: AsyncClient, token: str, name: str = "分类测试家") -> dict:
    """建一个家庭组。分类是挂在家庭组下面的，所以每个用例都先建一个。"""
    response = await client.post("/api/v1/spaces", json={"name": name}, headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _categories(client: AsyncClient, token: str, space_id: int) -> list[dict]:
    """取分类列表。"""
    response = await client.get(f"/api/v1/spaces/{space_id}/categories", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _category_id(client: AsyncClient, token: str, space_id: int, name: str) -> int:
    """按名字取分类 id。"""
    for item in await _categories(client, token, space_id):
        if item["name"] == name:
            return int(item["id"])
    raise AssertionError(f"家庭组 {space_id} 里没有找到分类「{name}」")


async def _add_recipe(client: AsyncClient, token: str, space_id: int, category_id: int, name: str = "番茄炒蛋") -> dict:
    """往某个分类下加一道菜。"""
    response = await client.post(
        f"/api/v1/spaces/{space_id}/recipes",
        json={"name": name, "category_id": category_id},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ==================== 默认分类 ====================


async def test_new_space_comes_with_default_categories(client: AsyncClient, login_as) -> None:
    """新建家庭组要自动带上一套默认分类，顺序不能乱。

    这件事必须做：没有分类的家，侧边栏是空的，用户连"加一道菜"都无从下手
    （新增菜品必须选分类）。所以"建组"和"建默认分类"是一件事的两个部分。
    """
    token, _ = await login_as("category-defaults")
    space = await _create_space(client, token)

    categories = await _categories(client, token, space["id"])

    assert [item["name"] for item in categories] == EXPECTED_DEFAULT_CATEGORIES
    # sort_order 必须是 0..5 递增，顺序是前端侧边栏的显示顺序
    assert [item["sort_order"] for item in categories] == [0, 1, 2, 3, 4, 5]
    # 刚建好的家一道菜都没有，每个分类的数量都应该是 0
    assert all(item["recipe_count"] == 0 for item in categories)
    # 「热菜」是新增菜品时的默认选中项
    assert [item["name"] for item in categories if item["is_default"]] == ["热菜"]


async def test_default_categories_are_per_space(client: AsyncClient, login_as) -> None:
    """每个家庭组有自己的那一套分类，互不影响。"""
    first_token, _ = await login_as("defaults-first")
    first_space = await _create_space(client, first_token, "甲家")

    second_token, _ = await login_as("defaults-second")
    second_space = await _create_space(client, second_token, "乙家")

    first_ids = {item["id"] for item in await _categories(client, first_token, first_space["id"])}
    second_ids = {item["id"] for item in await _categories(client, second_token, second_space["id"])}

    # 两家的分类是各自独立的记录，id 不可能重合
    assert not (first_ids & second_ids)


# ==================== 新增与改名 ====================


async def test_create_category_appends_to_the_end(client: AsyncClient, login_as) -> None:
    """新增的分类排在最后，不会插到默认分类中间去。"""
    token, _ = await login_as("category-create")
    space = await _create_space(client, token)

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/categories",
        json={"name": "早餐"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    created = response.json()["data"]
    assert created["name"] == "早餐"
    assert created["recipe_count"] == 0
    # 默认分类占 0..5，新加的排在后面
    assert created["sort_order"] == 6

    assert [item["name"] for item in await _categories(client, token, space["id"])] == [
        *EXPECTED_DEFAULT_CATEGORIES,
        "早餐",
    ]


async def test_reorder_categories_updates_menu_order(client: AsyncClient, login_as) -> None:
    """完整排序后，分类接口按新顺序返回且菜品归属不变。"""
    token, _ = await login_as("category-reorder")
    space = await _create_space(client, token)
    categories = await _categories(client, token, space["id"])
    ordered = [item["id"] for item in categories]
    ordered[0], ordered[1] = ordered[1], ordered[0]

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/categories/reorder",
        json={"category_ids": ordered},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["data"]] == ordered
    assert [item["sort_order"] for item in response.json()["data"]] == list(range(len(ordered)))


async def test_reorder_categories_rejects_incomplete_or_duplicate_ids(client: AsyncClient, login_as) -> None:
    """缺分类或重复 ID 不能让顺序数据被部分覆盖。"""
    token, _ = await login_as("category-reorder-invalid")
    space = await _create_space(client, token)
    categories = await _categories(client, token, space["id"])
    ids = [item["id"] for item in categories]

    for invalid_ids in (ids[:-1], [*ids[:-1], ids[0]]):
        response = await client.post(
            f"/api/v1/spaces/{space['id']}/categories/reorder",
            json={"category_ids": invalid_ids},
            headers=_auth(token),
        )
        assert response.status_code == 400, response.text

    assert [item["id"] for item in await _categories(client, token, space["id"])] == ids


async def test_non_owner_cannot_reorder_categories(client: AsyncClient, login_as) -> None:
    """分类顺序与菜单设置一样，只允许家庭创建人修改。"""
    owner_token, _ = await login_as("category-reorder-owner")
    space = await _create_space(client, owner_token)
    categories = await _categories(client, owner_token, space["id"])

    member_token, _ = await login_as("category-reorder-member")
    joined = await client.post(
        "/api/v1/spaces/join",
        json={"invite_code": space["invite_code"]},
        headers=_auth(member_token),
    )
    assert joined.status_code == 200, joined.text

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/categories/reorder",
        json={"category_ids": [item["id"] for item in reversed(categories)]},
        headers=_auth(member_token),
    )
    assert response.status_code == 403, response.text


async def test_rename_category_keeps_recipes_attached(client: AsyncClient, login_as) -> None:
    """改了分类名，原来挂在这个分类下的菜要跟着显示新名字。

    这是"菜谱存 category_id 外键、而不是存分类名字符串"最直接的好处：
    改名只需要动这一行，不用去批量更新菜谱表。
    如果当初存的是名字，这条测试就会变成"改名后菜谱还必须被逐个改一遍"。

    注意同时验证了改名之后菜的 category_id **没有变**——
    变了的话说明实现上走了"删旧分类、建新分类"的歪路，菜谱会跟着丢。
    """
    token, _ = await login_as("category-rename")
    space = await _create_space(client, token)
    hot_id = await _category_id(client, token, space["id"], "热菜")
    await _add_recipe(client, token, space["id"], hot_id, name="番茄炒蛋")

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/categories/{hot_id}",
        json={"name": "家常热菜"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["name"] == "家常热菜"
    # 菜谱数量没变，说明菜还挂在这个分类上
    assert response.json()["data"]["recipe_count"] == 1

    listed = await client.get(f"/api/v1/spaces/{space['id']}/recipes", headers=_auth(token))
    recipe = listed.json()["data"]["recipes"][0]
    assert recipe["category_name"] == "家常热菜"
    assert recipe["category_id"] == hot_id


async def test_rename_without_change_is_accepted(client: AsyncClient, login_as) -> None:
    """名字没变也允许保存，不该报错。

    前端"点开改名、看了一眼、又原样保存"是很常见的操作，
    没必要判成失败，也顺便省掉一条没有意义的 UPDATE。
    """
    token, _ = await login_as("category-rename-same")
    space = await _create_space(client, token)
    hot_id = await _category_id(client, token, space["id"], "热菜")

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/categories/{hot_id}",
        json={"name": "热菜"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text


# ==================== 重名拦截 ====================


async def test_duplicate_category_name_is_rejected(client: AsyncClient, login_as) -> None:
    """同一个家里不能有两个同名分类。"""
    token, _ = await login_as("category-duplicate")
    space = await _create_space(client, token)

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/categories",
        json={"name": "热菜"},
        headers=_auth(token),
    )

    assert response.status_code == 400, response.text
    assert "热菜" in response.json()["message"]


async def test_rename_to_existing_name_is_rejected(client: AsyncClient, login_as) -> None:
    """改名改成另一个已存在的分类名，也要拦住。

    新增和改名是两条独立的代码路径，很容易只堵住一条。
    """
    token, _ = await login_as("category-rename-dup")
    space = await _create_space(client, token)
    cold_id = await _category_id(client, token, space["id"], "凉菜")

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/categories/{cold_id}",
        json={"name": "热菜"},
        headers=_auth(token),
    )

    assert response.status_code == 400, response.text
    assert "热菜" in response.json()["message"]


async def test_same_name_can_be_used_in_different_spaces(client: AsyncClient, login_as) -> None:
    """重名的限制只在同一个家里生效，不同家庭组之间互不影响。

    这条是验证唯一约束是 (space_id, name) 两列，
    而不是只约束 name —— 否则"凉菜"这个名字全平台就只有一个人能用了。
    """
    first_token, _ = await login_as("dup-name-first")
    first_space = await _create_space(client, first_token, "甲家")

    second_token, _ = await login_as("dup-name-second")
    second_space = await _create_space(client, second_token, "乙家")

    response = await client.post(
        f"/api/v1/spaces/{second_space['id']}/categories",
        json={"name": "早餐"},
        headers=_auth(second_token),
    )
    assert response.status_code == 200, response.text

    same_name_in_first = await client.post(
        f"/api/v1/spaces/{first_space['id']}/categories",
        json={"name": "早餐"},
        headers=_auth(first_token),
    )
    assert same_name_in_first.status_code == 200, same_name_in_first.text


# ==================== 删除保护 ====================


async def test_delete_empty_category_succeeds(client: AsyncClient, login_as) -> None:
    """删掉一个没有菜的分类，应该成功。"""
    token, _ = await login_as("category-delete")
    space = await _create_space(client, token)
    dessert_id = await _category_id(client, token, space["id"], "甜点")

    response = await client.delete(
        f"/api/v1/spaces/{space['id']}/categories/{dessert_id}",
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert [item["name"] for item in await _categories(client, token, space["id"])] == [
        "凉菜",
        "热菜",
        "汤羹",
        "主食",
        "饮品",
    ]


async def test_delete_category_with_recipes_is_rejected(client: AsyncClient, login_as) -> None:
    """分类下还有菜时拒绝删除，并且要告诉用户有几道菜。

    这是这批功能里最重要的一条保护：
    如果允许直接删，那些菜就失去了归属，既搜不到也显示不出来，等于凭空消失。
    提示里带上具体数量，用户才知道"先去移走几道"。
    """
    token, _ = await login_as("category-delete-guard")
    space = await _create_space(client, token)
    hot_id = await _category_id(client, token, space["id"], "热菜")
    await _add_recipe(client, token, space["id"], hot_id, name="番茄炒蛋")
    await _add_recipe(client, token, space["id"], hot_id, name="红烧肉")

    response = await client.delete(
        f"/api/v1/spaces/{space['id']}/categories/{hot_id}",
        headers=_auth(token),
    )

    assert response.status_code == 400, response.text
    message = response.json()["message"]
    assert "2" in message  # 要说出有几道菜
    assert "热菜" in message

    # 关键：被拒绝之后，分类和里面的菜都必须原封不动
    categories = {item["name"]: item for item in await _categories(client, token, space["id"])}
    assert categories["热菜"]["recipe_count"] == 2

    listed = await client.get(f"/api/v1/spaces/{space['id']}/recipes", headers=_auth(token))
    assert [item["name"] for item in listed.json()["data"]["recipes"]] == ["番茄炒蛋", "红烧肉"]


async def test_can_delete_category_after_moving_recipes_away(client: AsyncClient, login_as) -> None:
    """把菜移走之后，这个分类就能删了——这是完整的使用流程。"""
    token, _ = await login_as("category-move-then-delete")
    space = await _create_space(client, token)
    hot_id = await _category_id(client, token, space["id"], "热菜")
    cold_id = await _category_id(client, token, space["id"], "凉菜")
    recipe = await _add_recipe(client, token, space["id"], hot_id, name="拍黄瓜")

    # 先改到别的分类
    moved = await client.patch(
        f"/api/v1/spaces/{space['id']}/recipes/{recipe['id']}",
        json={"category_id": cold_id},
        headers=_auth(token),
    )
    assert moved.status_code == 200, moved.text

    # 再删这个已经空掉的分类
    deleted = await client.delete(
        f"/api/v1/spaces/{space['id']}/categories/{hot_id}",
        headers=_auth(token),
    )

    assert deleted.status_code == 200, deleted.text
    remaining = [item["name"] for item in await _categories(client, token, space["id"])]
    assert "热菜" not in remaining

    # 菜还在，只是换了分类
    listed = await client.get(f"/api/v1/spaces/{space['id']}/recipes", headers=_auth(token))
    assert listed.json()["data"]["recipes"][0]["category_name"] == "凉菜"


# ==================== 参数与权限边界 ====================


async def test_create_category_with_blank_name_is_rejected(client: AsyncClient, login_as) -> None:
    """全是空格的名字不能存进去。

    Pydantic 的 min_length 只看字符数，"   " 有 3 个字符能过，
    所以要靠 Service 层兜住。
    """
    token, _ = await login_as("category-blank-name")
    space = await _create_space(client, token)

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/categories",
        json={"name": "   "},
        headers=_auth(token),
    )

    assert response.status_code == 400, response.text
    assert "分类" in response.json()["message"]


async def test_non_member_cannot_read_categories(client: AsyncClient, login_as) -> None:
    """不是家庭成员的人，连分类清单都不能看。"""
    owner_token, _ = await login_as("cat-priv-owner")
    space = await _create_space(client, owner_token)

    stranger_token, _ = await login_as("cat-priv-stranger")
    response = await client.get(
        f"/api/v1/spaces/{space['id']}/categories",
        headers=_auth(stranger_token),
    )

    assert response.status_code == 403


async def test_non_member_cannot_write_categories(client: AsyncClient, login_as) -> None:
    """不是家庭成员的人，新增、改名、删除分类都要被拒绝。"""
    owner_token, _ = await login_as("cat-write-owner")
    space = await _create_space(client, owner_token)
    hot_id = await _category_id(client, owner_token, space["id"], "热菜")

    stranger_token, _ = await login_as("cat-write-stranger")
    headers = _auth(stranger_token)

    created = await client.post(
        f"/api/v1/spaces/{space['id']}/categories",
        json={"name": "陌生人加的分类"},
        headers=headers,
    )
    renamed = await client.post(
        f"/api/v1/spaces/{space['id']}/categories/{hot_id}",
        json={"name": "陌生人改的名字"},
        headers=headers,
    )
    deleted = await client.delete(
        f"/api/v1/spaces/{space['id']}/categories/{hot_id}",
        headers=headers,
    )

    assert created.status_code == 403
    assert renamed.status_code == 403
    assert deleted.status_code == 403


async def test_category_from_another_space_is_invisible(client: AsyncClient, login_as) -> None:
    """用自己的家庭组 ID 去猜别人家的分类 ID，必须改不了也删不掉。

    和菜谱那边同理：对外统一返回"分类不存在"（404），
    不区分"真没有"和"不属于这个家"，免得别人拿状态码差异去试探。
    """
    first_token, _ = await login_as("cat-cross-first")
    first_space = await _create_space(client, first_token, "甲家")

    second_token, _ = await login_as("cat-cross-second")
    second_space = await _create_space(client, second_token, "乙家")
    foreign_category_id = await _category_id(client, second_token, second_space["id"], "热菜")

    headers = _auth(first_token)
    renamed = await client.post(
        f"/api/v1/spaces/{first_space['id']}/categories/{foreign_category_id}",
        json={"name": "改别人家的分类"},
        headers=headers,
    )
    deleted = await client.delete(
        f"/api/v1/spaces/{first_space['id']}/categories/{foreign_category_id}",
        headers=headers,
    )

    assert renamed.status_code == 404
    assert deleted.status_code == 404

    # 确认别人家的分类确实没被动过
    foreign_categories = await _categories(client, second_token, second_space["id"])
    assert "热菜" in [item["name"] for item in foreign_categories]


async def test_categories_require_login(client: AsyncClient, login_as) -> None:
    """未登录不能读写分类。"""
    token, _ = await login_as("cat-anonymous")
    space = await _create_space(client, token)
    hot_id = await _category_id(client, token, space["id"], "热菜")

    listed = await client.get(f"/api/v1/spaces/{space['id']}/categories")
    created = await client.post(
        f"/api/v1/spaces/{space['id']}/categories",
        json={"name": "匿名加的分类"},
    )
    renamed = await client.post(
        f"/api/v1/spaces/{space['id']}/categories/{hot_id}",
        json={"name": "匿名改的名字"},
    )
    deleted = await client.delete(f"/api/v1/spaces/{space['id']}/categories/{hot_id}")

    assert listed.status_code == 401
    assert created.status_code == 401
    assert renamed.status_code == 401
    assert deleted.status_code == 401


# ==================== 小程序兼容入口（POST 改分类） ====================


async def test_rename_via_post_entry_is_registered(client: AsyncClient, login_as) -> None:
    """改分类的 POST 入口要真的注册上了。

    这里用"未登录访问返回 401 而不是 405"来判断：
    405（方法不允许）意味着这个路径上根本没有 POST 路由，
    401 才说明路由在、只是挡住了未登录的请求。
    """
    token, _ = await login_as("cat-post-entry")
    space = await _create_space(client, token)
    hot_id = await _category_id(client, token, space["id"], "热菜")

    anonymous = await client.post(
        f"/api/v1/spaces/{space['id']}/categories/{hot_id}",
        json={"name": "随便改改"},
    )

    assert anonymous.status_code == 401, anonymous.text
