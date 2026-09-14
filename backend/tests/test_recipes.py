"""家庭菜谱接口测试。

覆盖六类行为：
    1. 正常增删改查：新增、列表、详情、部分更新、删除；
    2. 分类必填且必须属于本家：不传分类、传不存在的分类、传别人家的分类都要被拦住；
    3. 筛选：按分类筛、按关键词搜（菜名和做法都能搜到）；
    4. 权限边界：非成员读写一律被拒；跨家庭组拿别人的菜谱 ID 也读不到；
    5. 参数与登录态：空菜名、未登录的处理是否合理；
    6. 小程序兼容入口：POST 改菜谱与 PATCH 行为一致，且不绕过鉴权。

关于测试数据：和家庭组测试一样直接跑在本地开发库上，
每个用例用随机后缀的临时用户，所以可以反复运行而不会互相干扰。
"""

from httpx import AsyncClient

# 分类顺序是后端定的契约，这里写死是为了"哪天有人改了顺序"能立刻被发现
EXPECTED_CATEGORIES = ["凉菜", "热菜", "汤羹", "主食", "甜点", "饮品"]


def _auth(token: str) -> dict[str, str]:
    """构造带令牌的请求头。"""
    return {"Authorization": f"Bearer {token}"}


async def _create_space(client: AsyncClient, token: str, name: str = "菜谱测试家") -> dict:
    """建一个家庭组。菜谱必须挂在家庭组下面，所以每个用例都先建一个。"""
    response = await client.post("/api/v1/spaces", json={"name": name}, headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _categories(client: AsyncClient, token: str, space_id: int) -> list[dict]:
    """取某个家庭组的分类列表。"""
    response = await client.get(f"/api/v1/spaces/{space_id}/categories", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _category_id(client: AsyncClient, token: str, space_id: int, name: str = "热菜") -> int:
    """按名字取分类 id。

    测试里按名字找更好读（"这道菜归到凉菜"比"归到 id=37"更像人话），
    但接口之间传的是 id——名字是可以被用户改的，id 才是稳定的。
    """
    for item in await _categories(client, token, space_id):
        if item["name"] == name:
            return int(item["id"])
    raise AssertionError(f"家庭组 {space_id} 里没有找到分类「{name}」")


async def _add_recipe(client: AsyncClient, token: str, space_id: int, **overrides) -> dict:
    """往家庭组里加一道菜。字段可以用关键字参数覆盖。

    category 参数收的是分类**名字**，内部会翻译成 id 再发给接口——
    这样测试读起来仍然是"归到热菜"，而不是一串数字。
    """
    category_name = overrides.pop("category", "热菜")
    payload = {
        "name": "番茄炒蛋",
        "category_id": await _category_id(client, token, space_id, category_name),
        "description": "鸡蛋先炒散，番茄去皮。",
    }
    payload.update(overrides)

    response = await client.post(f"/api/v1/spaces/{space_id}/recipes", json=payload, headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ==================== 正常路径 ====================


async def test_create_recipe_assigns_chosen_category(client: AsyncClient, login_as) -> None:
    """新增菜谱时选择合适的分类，并正确记录归属和添加者。"""
    token, user_id = await login_as("recipe-create")
    space = await _create_space(client, token)
    category_id = await _category_id(client, token, space["id"], "汤羹")

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes",
        json={"name": "冬瓜排骨汤", "category_id": category_id},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["category_id"] == category_id
    # 分类名也一起返回，前端不用自己去分类清单里查
    assert data["category_name"] == "汤羹"
    assert data["space_id"] == space["id"]
    assert data["created_by"] == user_id
    assert data["created_by_nickname"]
    assert data["description"] is None


async def test_created_recipe_appears_in_list_with_categories(client: AsyncClient, login_as) -> None:
    """建好的菜要出现在列表里，按添加先后排序，并带上分类清单。"""
    token, _ = await login_as("recipe-list")
    space = await _create_space(client, token)
    await _add_recipe(client, token, space["id"], name="拍黄瓜", category="凉菜")
    await _add_recipe(client, token, space["id"], name="番茄炒蛋", category="热菜")

    response = await client.get(f"/api/v1/spaces/{space['id']}/recipes", headers=_auth(token))

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [item["name"] for item in data["categories"]] == EXPECTED_CATEGORIES
    assert [item["name"] for item in data["recipes"]] == ["拍黄瓜", "番茄炒蛋"]


async def test_list_categories_carry_count_and_default_flag(client: AsyncClient, login_as) -> None:
    """分类清单要带上每类的菜数和"默认选中"标记。

    菜数由后端算（全量口径），不是前端自己数过滤后的结果——
    否则用户一搜索，侧边栏上的数字就跟着变，看着很奇怪。

    is_default 是给前端新增菜品时用的：编辑器一打开就选中「热菜」，
    省得每次加菜都要手动改一下分类。
    """
    token, _ = await login_as("category-meta")
    space = await _create_space(client, token)
    await _add_recipe(client, token, space["id"], name="拍黄瓜", category="凉菜")
    await _add_recipe(client, token, space["id"], name="番茄炒蛋", category="热菜")
    await _add_recipe(client, token, space["id"], name="青椒肉丝", category="热菜")

    response = await client.get(f"/api/v1/spaces/{space['id']}/recipes", headers=_auth(token))
    categories = {item["name"]: item for item in response.json()["data"]["categories"]}

    assert categories["凉菜"]["recipe_count"] == 1
    assert categories["热菜"]["recipe_count"] == 2
    # 一道菜都没有的分类也要出现（这里是 OUTER JOIN 而不是 INNER JOIN 的意义）
    assert categories["甜点"]["recipe_count"] == 0

    defaults = [name for name, item in categories.items() if item["is_default"]]
    assert defaults == ["热菜"]


async def test_get_recipe_detail(client: AsyncClient, login_as) -> None:
    """详情接口要能按 id 取到单条菜谱。"""
    token, _ = await login_as("recipe-detail")
    space = await _create_space(client, token)
    created = await _add_recipe(client, token, space["id"], name="红烧肉", description="小火慢炖一小时。")

    response = await client.get(
        f"/api/v1/spaces/{space['id']}/recipes/{created['id']}",
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["id"] == created["id"]
    assert data["name"] == "红烧肉"
    assert data["description"] == "小火慢炖一小时。"
    assert data["category_name"] == "热菜"


async def test_update_only_changes_given_fields(client: AsyncClient, login_as) -> None:
    """部分更新：只改传过来的字段，没传的保持原样。

    这条是防"改一个备注顺手把菜名清了"这类事故的关键。
    """
    token, _ = await login_as("recipe-patch")
    space = await _create_space(client, token)
    created = await _add_recipe(client, token, space["id"], name="番茄炒蛋", category="热菜")

    response = await client.patch(
        f"/api/v1/spaces/{space['id']}/recipes/{created['id']}",
        json={"description": "番茄要先用开水烫一下好去皮。"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["description"] == "番茄要先用开水烫一下好去皮。"
    assert data["name"] == "番茄炒蛋"
    assert data["category_name"] == "热菜"


async def test_update_can_change_category(client: AsyncClient, login_as) -> None:
    """换分类是支持的，而且返回的分类名要跟着变。"""
    token, _ = await login_as("recipe-move-category")
    space = await _create_space(client, token)
    created = await _add_recipe(client, token, space["id"], name="拍黄瓜", category="热菜")

    cold_id = await _category_id(client, token, space["id"], "凉菜")
    response = await client.patch(
        f"/api/v1/spaces/{space['id']}/recipes/{created['id']}",
        json={"category_id": cold_id},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["category_id"] == cold_id
    # 分类名必须跟着变——如果这里还返回"热菜"，前端会显示错
    assert data["category_name"] == "凉菜"


async def test_update_can_clear_description(client: AsyncClient, login_as) -> None:
    """显式传 null 表示"把做法清空"，和"没传这个字段"是两回事。"""
    token, _ = await login_as("recipe-clear")
    space = await _create_space(client, token)
    created = await _add_recipe(client, token, space["id"], description="先这样再那样。")

    response = await client.patch(
        f"/api/v1/spaces/{space['id']}/recipes/{created['id']}",
        json={"description": None},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["description"] is None


async def test_delete_recipe_removes_it_from_list(client: AsyncClient, login_as) -> None:
    """删掉之后列表里就不该再有它。"""
    token, _ = await login_as("recipe-delete")
    space = await _create_space(client, token)
    created = await _add_recipe(client, token, space["id"])

    deleted = await client.delete(
        f"/api/v1/spaces/{space['id']}/recipes/{created['id']}",
        headers=_auth(token),
    )
    listed = await client.get(f"/api/v1/spaces/{space['id']}/recipes", headers=_auth(token))

    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["code"] == 0
    assert listed.json()["data"]["recipes"] == []


async def test_list_shows_who_added_each_recipe(client: AsyncClient, login_as) -> None:
    """列表要带出「谁加的」，而且必须对得上人。

    这条验证 repository 里那次 join 是选对了行——
    否则前端会把"爸加的菜"显示成"妈加的"。

    ⚠️ 菜单写操作现在**只有创建人能做**，所以同一个家里不可能出现两个作者。
    要区分"join 有没有选对行"，就造两个家、两个创建人：
    甲建 A 家、乙建 B 家，然后互相加入（这样甲能同时看到两份列表），
    各自在自己建的家里加一道菜。甲读 A 家应看到自己的 ID、读 B 家应看到乙的 ID——
    join 要是选错了行，这两条就会串。

    说明：开发模式下用户都是自动注册的，昵称都是同一个默认值，
    所以昵称本身区分不出是谁；能真正区分的是 created_by 这个用户 ID，
    因此这里重点断言 ID 对得上，昵称只断言"有值"。
    """
    token_a, id_a = await login_as("author-a")
    space_a = await _create_space(client, token_a)

    token_b, id_b = await login_as("author-b")
    space_b = await _create_space(client, token_b)

    # 互相加入：让甲同时是 A 家（自己建的）和 B 家（乙建的）的成员
    joined_b = await client.post(
        "/api/v1/spaces/join",
        json={"invite_code": space_b["invite_code"]},
        headers=_auth(token_a),
    )
    assert joined_b.status_code == 200, joined_b.text
    joined_a = await client.post(
        "/api/v1/spaces/join",
        json={"invite_code": space_a["invite_code"]},
        headers=_auth(token_b),
    )
    assert joined_a.status_code == 200, joined_a.text

    # 各自只在自己建的家里加菜
    await _add_recipe(client, token_a, space_a["id"], name="红烧肉")
    await _add_recipe(client, token_b, space_b["id"], name="拍黄瓜", category="凉菜")

    listing_a = await client.get(f"/api/v1/spaces/{space_a['id']}/recipes", headers=_auth(token_a))
    listing_b = await client.get(f"/api/v1/spaces/{space_b['id']}/recipes", headers=_auth(token_a))

    assert listing_a.status_code == 200, listing_a.text
    assert listing_b.status_code == 200, listing_b.text

    item_a = listing_a.json()["data"]["recipes"][0]
    item_b = listing_b.json()["data"]["recipes"][0]

    assert item_a["name"] == "红烧肉"
    assert item_a["created_by"] == id_a
    assert item_a["created_by_nickname"]

    assert item_b["name"] == "拍黄瓜"
    assert item_b["created_by"] == id_b
    assert item_b["created_by_nickname"]


# ==================== 筛选与搜索 ====================


async def test_list_can_filter_by_category(client: AsyncClient, login_as) -> None:
    """按分类筛选只返回该分类的菜。"""
    token, _ = await login_as("filter-category")
    space = await _create_space(client, token)
    await _add_recipe(client, token, space["id"], name="拍黄瓜", category="凉菜")
    await _add_recipe(client, token, space["id"], name="番茄炒蛋", category="热菜")

    cold_id = await _category_id(client, token, space["id"], "凉菜")
    response = await client.get(
        f"/api/v1/spaces/{space['id']}/recipes",
        params={"category_id": cold_id},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert [item["name"] for item in response.json()["data"]["recipes"]] == ["拍黄瓜"]


async def test_filter_by_foreign_category_returns_empty(client: AsyncClient, login_as) -> None:
    """用别人家的分类 id 来筛选，只能得到空列表，绝不能读到别人家的菜。

    注意这里返回 200 + 空数组，而不是报错：筛选条件本身是"叠加"上去的，
    查询里还带着"必须是这个家庭组"这个条件，所以天然查不到别家的数据。
    """
    first_token, _ = await login_as("filter-foreign-first")
    first_space = await _create_space(client, first_token, "甲家")
    await _add_recipe(client, first_token, first_space["id"], name="甲家的菜")

    second_token, _ = await login_as("filter-foreign-second")
    second_space = await _create_space(client, second_token, "乙家")
    foreign_category_id = await _category_id(client, second_token, second_space["id"], "热菜")

    response = await client.get(
        f"/api/v1/spaces/{first_space['id']}/recipes",
        params={"category_id": foreign_category_id},
        headers=_auth(first_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["recipes"] == []


async def test_search_matches_name_and_description(client: AsyncClient, login_as) -> None:
    """关键词搜索同时覆盖菜名和做法。

    为什么做法也要搜？家人常常记得"里面放木耳的那道菜"，却想不起菜名。
    """
    token, _ = await login_as("search-keyword")
    space = await _create_space(client, token)
    await _add_recipe(client, token, space["id"], name="木须肉", description="木耳、鸡蛋、黄瓜片一起炒。")
    await _add_recipe(client, token, space["id"], name="番茄炒蛋", description="鸡蛋先炒散。")

    by_name = await client.get(
        f"/api/v1/spaces/{space['id']}/recipes",
        params={"keyword": "木须"},
        headers=_auth(token),
    )
    by_description = await client.get(
        f"/api/v1/spaces/{space['id']}/recipes",
        params={"keyword": "木耳"},
        headers=_auth(token),
    )

    assert [item["name"] for item in by_name.json()["data"]["recipes"]] == ["木须肉"]
    assert [item["name"] for item in by_description.json()["data"]["recipes"]] == ["木须肉"]


async def test_search_treats_wildcard_characters_as_plain_text(client: AsyncClient, login_as) -> None:
    """搜索里的 % 和 _ 必须当普通字符处理，不能当通配符。

    如果不转义，搜一个 % 就会把所有菜都搜出来——用户会以为搜索坏了，
    而且这种做法在数据量大时会变成全表扫描。
    """
    token, _ = await login_as("search-wildcard")
    space = await _create_space(client, token)
    await _add_recipe(client, token, space["id"], name="红烧肉")
    await _add_recipe(client, token, space["id"], name="拍黄瓜", category="凉菜")

    percent = await client.get(
        f"/api/v1/spaces/{space['id']}/recipes",
        params={"keyword": "%"},
        headers=_auth(token),
    )
    underscore = await client.get(
        f"/api/v1/spaces/{space['id']}/recipes",
        params={"keyword": "_"},
        headers=_auth(token),
    )

    assert percent.json()["data"]["recipes"] == []
    assert underscore.json()["data"]["recipes"] == []


# ==================== 权限边界 ====================


async def test_non_member_cannot_read_recipes(client: AsyncClient, login_as) -> None:
    """不是家庭成员的人，读列表和详情都必须被拒绝。"""
    owner_token, _ = await login_as("priv-recipes-owner")
    space = await _create_space(client, owner_token)
    created = await _add_recipe(client, owner_token, space["id"])

    stranger_token, _ = await login_as("priv-recipes-stranger")
    headers = _auth(stranger_token)

    listed = await client.get(f"/api/v1/spaces/{space['id']}/recipes", headers=headers)
    detail = await client.get(f"/api/v1/spaces/{space['id']}/recipes/{created['id']}", headers=headers)

    assert listed.status_code == 403
    assert detail.status_code == 403


async def test_non_member_cannot_write_recipes(client: AsyncClient, login_as) -> None:
    """不是家庭成员的人，新增、修改、删除菜谱都必须被拒绝。"""
    owner_token, _ = await login_as("write-recipes-owner")
    space = await _create_space(client, owner_token)
    created = await _add_recipe(client, owner_token, space["id"])
    category_id = await _category_id(client, owner_token, space["id"], "热菜")

    stranger_token, _ = await login_as("write-recipes-stranger")
    headers = _auth(stranger_token)

    created_response = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes",
        json={"name": "偷偷加的菜", "category_id": category_id},
        headers=headers,
    )
    updated = await client.patch(
        f"/api/v1/spaces/{space['id']}/recipes/{created['id']}",
        json={"name": "偷偷改的菜"},
        headers=headers,
    )
    deleted = await client.delete(
        f"/api/v1/spaces/{space['id']}/recipes/{created['id']}",
        headers=headers,
    )

    assert created_response.status_code == 403
    assert updated.status_code == 403
    assert deleted.status_code == 403


async def test_recipe_from_another_space_is_invisible(client: AsyncClient, login_as) -> None:
    """用自己的家庭组 ID 去猜别人家的菜谱 ID，必须读不到也改不了。

    这是最典型的越权漏洞：菜谱 ID 是自增的，很容易被猜到。
    注意这里返回 404 而不是 403——对外不区分"不存在"和"不是你的"，
    免得别人拿脚本一个个试，靠状态码差异摸清哪些 ID 是真的。
    """
    first_token, _ = await login_as("cross-space-first")
    first_space = await _create_space(client, first_token, "甲家")

    second_token, _ = await login_as("cross-space-second")
    second_space = await _create_space(client, second_token, "乙家")
    foreign_recipe = await _add_recipe(client, second_token, second_space["id"], name="别人家的菜")

    headers = _auth(first_token)
    detail = await client.get(
        f"/api/v1/spaces/{first_space['id']}/recipes/{foreign_recipe['id']}",
        headers=headers,
    )
    updated = await client.patch(
        f"/api/v1/spaces/{first_space['id']}/recipes/{foreign_recipe['id']}",
        json={"name": "改别人家的菜"},
        headers=headers,
    )
    deleted = await client.delete(
        f"/api/v1/spaces/{first_space['id']}/recipes/{foreign_recipe['id']}",
        headers=headers,
    )

    assert detail.status_code == 404
    assert updated.status_code == 404
    assert deleted.status_code == 404

    # 再确认"别人家的菜"确实没被动过
    still_there = await client.get(
        f"/api/v1/spaces/{second_space['id']}/recipes/{foreign_recipe['id']}",
        headers=_auth(second_token),
    )
    assert still_there.status_code == 200
    assert still_there.json()["data"]["name"] == "别人家的菜"


# ==================== 参数与登录态 ====================


async def test_create_recipe_without_category_is_rejected(client: AsyncClient, login_as) -> None:
    """不传分类必须被拒绝，而不是悄悄塞进某个分类。

    第一版有"不传就默认归到热菜"的行为，改成可自定义分类之后取消了：
    分类是用户自己的数据，后端没有理由替他决定这道菜属于哪一类。
    """
    token, _ = await login_as("recipe-no-category")
    space = await _create_space(client, token)

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes",
        json={"name": "清炒时蔬"},
        headers=_auth(token),
    )

    assert response.status_code == 422, response.text


async def test_create_recipe_with_unknown_category_is_rejected(client: AsyncClient, login_as) -> None:
    """传一个不存在的分类 id，要报"分类不存在"。"""
    token, _ = await login_as("recipe-bad-category")
    space = await _create_space(client, token)

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes",
        json={"name": "佛跳墙", "category_id": 99999999},
        headers=_auth(token),
    )

    assert response.status_code == 404, response.text
    assert "分类" in response.json()["message"]


async def test_cannot_attach_recipe_to_foreign_category(client: AsyncClient, login_as) -> None:
    """不能把菜挂到别人家的分类上。

    分类 ID 是自增的、可猜的。如果不校验归属，
    甲家的菜就能挂到乙家的分类下，数据会错乱，而且跨家庭组还能互相看见。
    """
    first_token, _ = await login_as("foreign-cat-first")
    first_space = await _create_space(client, first_token, "甲家")

    second_token, _ = await login_as("foreign-cat-second")
    second_space = await _create_space(client, second_token, "乙家")
    foreign_category_id = await _category_id(client, second_token, second_space["id"], "热菜")

    response = await client.post(
        f"/api/v1/spaces/{first_space['id']}/recipes",
        json={"name": "挂错家的菜", "category_id": foreign_category_id},
        headers=_auth(first_token),
    )

    assert response.status_code == 404, response.text
    assert "分类" in response.json()["message"]


async def test_cannot_move_recipe_to_foreign_category(client: AsyncClient, login_as) -> None:
    """修改菜谱时同样不能把菜挪到别人家的分类下。

    新增接口和修改接口是两条独立的代码路径，很容易只堵住一条。
    """
    first_token, _ = await login_as("move-foreign-first")
    first_space = await _create_space(client, first_token, "甲家")
    mine = await _add_recipe(client, first_token, first_space["id"], name="我的菜")

    second_token, _ = await login_as("move-foreign-second")
    second_space = await _create_space(client, second_token, "乙家")
    foreign_category_id = await _category_id(client, second_token, second_space["id"], "热菜")

    response = await client.patch(
        f"/api/v1/spaces/{first_space['id']}/recipes/{mine['id']}",
        json={"category_id": foreign_category_id},
        headers=_auth(first_token),
    )

    assert response.status_code == 404, response.text

    # 确认这条菜没有被改坏，还在原来的分类里
    detail = await client.get(
        f"/api/v1/spaces/{first_space['id']}/recipes/{mine['id']}",
        headers=_auth(first_token),
    )
    assert detail.json()["data"]["category_name"] == "热菜"


async def test_update_recipe_with_null_category_is_rejected(client: AsyncClient, login_as) -> None:
    """显式把分类传成 null 要被拦住。

    这是"语法上合法、语义上不成立"的情况：一道菜必须挂在某个分类下。
    与其让数据库抛一个违反非空约束的错误（用户看不懂），不如给一句人话。
    """
    token, _ = await login_as("recipe-null-category")
    space = await _create_space(client, token)
    created = await _add_recipe(client, token, space["id"])

    response = await client.patch(
        f"/api/v1/spaces/{space['id']}/recipes/{created['id']}",
        json={"category_id": None},
        headers=_auth(token),
    )

    assert response.status_code == 400, response.text
    assert "分类" in response.json()["message"]


async def test_create_recipe_with_blank_name_returns_400(client: AsyncClient, login_as) -> None:
    """全是空格的菜名不能存进去，而且要给出可读提示。

    注意这种"看起来有内容、其实全是空格"的情况 Pydantic 察觉不到（min_length 只看字符数），
    所以由 Service 层兜住。
    """
    token, _ = await login_as("recipe-blank-name")
    space = await _create_space(client, token)
    category_id = await _category_id(client, token, space["id"], "热菜")

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes",
        json={"name": "   ", "category_id": category_id},
        headers=_auth(token),
    )

    assert response.status_code == 400, response.text
    assert "菜名" in response.json()["message"]


async def test_recipes_require_login(client: AsyncClient, login_as) -> None:
    """未登录不能读写菜谱。"""
    token, _ = await login_as("recipe-anonymous")
    space = await _create_space(client, token)
    created = await _add_recipe(client, token, space["id"])
    category_id = await _category_id(client, token, space["id"], "热菜")

    listed = await client.get(f"/api/v1/spaces/{space['id']}/recipes")
    created_response = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes",
        json={"name": "匿名加的菜", "category_id": category_id},
    )
    deleted = await client.delete(f"/api/v1/spaces/{space['id']}/recipes/{created['id']}")

    assert listed.status_code == 401
    assert created_response.status_code == 401
    assert deleted.status_code == 401


# ==================== 小程序兼容入口（POST 改菜谱） ====================
#
# 为什么会有这一组：
#   微信小程序的 wx.request，官方 method 合法值里没有 PATCH，小程序端发不出 PATCH 请求。
#   所以后端给「修改菜谱」这个处理函数同时挂了 PATCH 和 POST 两个路由，行为必须完全一致。
#   多一条路由就多一个可能漏加校验的地方，这一组就是盯着它。


async def test_update_via_post_entry_matches_patch(client: AsyncClient, login_as) -> None:
    """POST 入口的行为必须和 PATCH 完全一致。

    除了能改成功，还要保证"部分更新"的语义同样成立——
    只传做法时，菜名和分类不能被顺手改掉。
    """
    token, _ = await login_as("recipe-post-update")
    space = await _create_space(client, token)
    created = await _add_recipe(client, token, space["id"], name="番茄炒蛋", category="热菜")

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes/{created['id']}",
        json={"description": "这是用 POST 入口改的做法。"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["description"] == "这是用 POST 入口改的做法。"
    assert data["name"] == "番茄炒蛋"
    assert data["category_name"] == "热菜"


async def test_post_update_entry_rejects_non_member(client: AsyncClient, login_as) -> None:
    """POST 入口不能绕过成员校验。

    这是新增路由最容易出错的地方：接口能跑通、功能也对，就是忘了鉴权。
    """
    owner_token, _ = await login_as("post-entry-owner")
    space = await _create_space(client, owner_token)
    created = await _add_recipe(client, owner_token, space["id"])

    stranger_token, _ = await login_as("post-entry-stranger")
    response = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes/{created['id']}",
        json={"name": "陌生人改的菜"},
        headers=_auth(stranger_token),
    )

    assert response.status_code == 403


async def test_post_update_entry_requires_login(client: AsyncClient, login_as) -> None:
    """POST 入口同样要登录才能用。"""
    token, _ = await login_as("post-entry-anonymous")
    space = await _create_space(client, token)
    created = await _add_recipe(client, token, space["id"])

    response = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes/{created['id']}",
        json={"name": "没登录改的菜"},
    )

    assert response.status_code == 401
