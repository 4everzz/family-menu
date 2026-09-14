"""个人收藏接口测试。

覆盖的行为：
    1. 默认收藏夹**永远**在列表第一位，即使一道菜都没收藏；
    2. 收藏 / 取消 / 重复收藏（挪分区）；
    3. 分区的增、删、重名拦截、数量上限；
    4. **删分区时里面的收藏退回默认收藏夹**（收藏不丢）；
    5. 权限边界：别人的分区拿不到、别人家的菜收不了、非成员查不到、未登录 401；
    6. 分区额度可配置（不许写死，将来接会员只改一个函数）。

关于测试数据：跑在本地开发库上，每个用例用随机后缀的临时用户，可反复运行。
"""

from httpx import AsyncClient

from app.core.config import settings


def _auth(token: str) -> dict[str, str]:
    """构造带令牌的请求头。"""
    return {"Authorization": f"Bearer {token}"}


async def _login(client: AsyncClient, login_as, prefix: str) -> str:
    """造一个临时用户，返回令牌。"""
    token, _ = await login_as(prefix)
    return token


async def _space_with_recipe(client: AsyncClient, token: str, prefix: str, name: str = "番茄炒蛋") -> dict:
    """建一个家庭组并在里面加一道菜，返回 {spaceId, recipeId}。"""
    created = await client.post(
        "/api/v1/spaces", json={"name": f"收藏测试-{prefix}"}, headers=_auth(token)
    )
    assert created.status_code == 200, created.text
    space = created.json()["data"]

    categories = await client.get(
        f"/api/v1/spaces/{space['id']}/categories", headers=_auth(token)
    )
    assert categories.status_code == 200, categories.text
    hot = next(
        item for item in categories.json()["data"] if item["name"] == "热菜"
    )

    recipe = await client.post(
        f"/api/v1/spaces/{space['id']}/recipes",
        json={"name": name, "category_id": hot["id"]},
        headers=_auth(token),
    )
    assert recipe.status_code == 200, recipe.text

    return {"spaceId": int(space["id"]), "recipeId": int(recipe.json()["data"]["id"])}


async def _partitions(client: AsyncClient, token: str) -> list[dict]:
    """读分区列表。"""
    response = await client.get("/api/v1/favorites/partitions", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _favorites(client: AsyncClient, token: str, partition_id: int | None) -> list[dict]:
    """读某个分区下的收藏。partition_id 传 None 即默认收藏夹。"""
    params = {} if partition_id is None else {"partition_id": partition_id}
    response = await client.get("/api/v1/favorites", params=params, headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]["favorites"]


async def _create_partition(client: AsyncClient, token: str, name: str) -> tuple[int, dict]:
    """建分区，返回 (状态码, 响应体)。"""
    response = await client.post(
        "/api/v1/favorites/partitions", json={"name": name}, headers=_auth(token)
    )
    return response.status_code, response.json()


# ==================== 默认收藏夹 ====================


async def test_default_partition_always_first_and_empty_at_start(
    client: AsyncClient, login_as
) -> None:
    """默认收藏夹不落库，但必须永远出现在列表第一位——哪怕一道菜都没收藏。

    这是最容易做错的一条：如果把它当成"首次收藏时才建的一行数据"，
    新用户进「我的收藏」会看到一个空列表，不知道该往哪收。
    """
    token = await _login(client, login_as, "fav-default")
    partitions = await _partitions(client, token)

    assert len(partitions) == 1
    assert partitions[0]["isDefault"] is True
    assert partitions[0]["id"] is None
    assert partitions[0]["name"] == "默认收藏夹"
    assert partitions[0]["count"] == 0


async def test_favorite_into_default_and_list_it(client: AsyncClient, login_as) -> None:
    """收藏时指定分区，菜会出现在那个分区里，摘要信息要带全。"""
    token = await _login(client, login_as, "fav-add")
    data = await _space_with_recipe(client, token, "fav-add", name="红烧肉")

    response = await client.post(
        f"/api/v1/favorites/{data['recipeId']}", json={}, headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["created"] is True
    assert response.json()["data"]["partitionId"] is None

    items = await _favorites(client, token, None)
    assert len(items) == 1
    assert items[0]["recipeId"] == data["recipeId"]
    assert items[0]["name"] == "红烧肉"
    assert items[0]["spaceId"] == data["spaceId"]
    assert items[0]["spaceName"]
    assert items[0]["partitionId"] is None

    # 默认栏的计数也要跟着变
    partitions = await _partitions(client, token)
    assert partitions[0]["count"] == 1


async def test_unfavorite_then_favoriting_again_works(client: AsyncClient, login_as) -> None:
    """取消收藏后再收藏，应该重新出现——取消是删除记录，不是打标记。"""
    token = await _login(client, login_as, "fav-toggle")
    data = await _space_with_recipe(client, token, "fav-toggle")

    first = await client.post(
        f"/api/v1/favorites/{data['recipeId']}", json={}, headers=_auth(token)
    )
    assert first.status_code == 200, first.text

    removed = await client.delete(
        f"/api/v1/favorites/{data['recipeId']}", headers=_auth(token)
    )
    assert removed.status_code == 200, removed.text
    assert await _favorites(client, token, None) == []

    # 再取消一次：已经没有了，应该 404 而不是假装成功
    again = await client.delete(
        f"/api/v1/favorites/{data['recipeId']}", headers=_auth(token)
    )
    assert again.status_code == 404, again.text

    # 重新收藏，应当恢复
    readded = await client.post(
        f"/api/v1/favorites/{data['recipeId']}", json={}, headers=_auth(token)
    )
    assert readded.status_code == 200, readded.text
    assert len(await _favorites(client, token, None)) == 1


# ==================== 分区 ====================


async def test_partition_create_rename_conflict_and_move(client: AsyncClient, login_as) -> None:
    """建分区、重复收藏时挪分区、重名拦截。"""
    token = await _login(client, login_as, "fav-part")
    data = await _space_with_recipe(client, token, "fav-part", name="拍黄瓜")

    # 建两个分区
    status, body = await _create_partition(client, token, "想吃")
    assert status == 200, body
    want_to_eat = body["data"]["id"]
    status, body = await _create_partition(client, token, "孩子爱吃")
    assert status == 200, body

    # 重名拦截
    status, body = await _create_partition(client, token, "想吃")
    assert status == 400, body
    assert "想吃" in body["message"]

    # 收藏时直接指定分区
    response = await client.post(
        f"/api/v1/favorites/{data['recipeId']}",
        json={"partition_id": want_to_eat},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text

    # 分区列表要显示各自的计数；默认栏为 0
    partitions = await _partitions(client, token)
    counts = {item["name"]: item["count"] for item in partitions}
    assert counts["想吃"] == 1
    assert counts["孩子爱吃"] == 0
    assert counts["默认收藏夹"] == 0

    # 重复收藏并指定默认栏（partition_id 不传）→ 应挪过去而不是报错
    response = await client.post(
        f"/api/v1/favorites/{data['recipeId']}", json={}, headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["created"] is False

    assert len(await _favorites(client, token, None)) == 1
    assert await _favorites(client, token, want_to_eat) == []


async def test_partition_limit_is_configurable(
    client: AsyncClient, login_as, monkeypatch
) -> None:
    """分区数量有上限，且上限来自配置而不是写死在代码里。"""
    monkeypatch.setattr(settings, "max_favorite_partitions", 2)

    token = await _login(client, login_as, "fav-limit")
    for index in range(2):
        status, body = await _create_partition(client, token, f"分区{index}")
        assert status == 200, body

    status, body = await _create_partition(client, token, "超出上限的")
    assert status == 400, body
    assert "上限" in body["message"]
    assert "2" in body["message"]

    # 默认收藏夹不占额度：把它收进来之后，仍然只有 2 个自定义分区的额度概念
    partitions = await _partitions(client, token)
    assert len(partitions) == 3  # 默认 + 2 个自定义


async def test_delete_partition_moves_favorites_back_to_default(
    client: AsyncClient, login_as
) -> None:
    """删分区时，里面的收藏退回默认收藏夹——删文件夹不该把菜一起带走。"""
    token = await _login(client, login_as, "fav-del")
    data = await _space_with_recipe(client, token, "fav-del", name="清蒸鱼")

    status, body = await _create_partition(client, token, "周末做")
    assert status == 200, body
    weekend = body["data"]["id"]

    response = await client.post(
        f"/api/v1/favorites/{data['recipeId']}",
        json={"partition_id": weekend},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    assert len(await _favorites(client, token, weekend)) == 1

    deleted = await client.delete(
        f"/api/v1/favorites/partitions/{weekend}", headers=_auth(token)
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["moved"] == 1

    # 收藏退回默认栏，而不是消失
    items = await _favorites(client, token, None)
    assert len(items) == 1
    assert items[0]["recipeId"] == data["recipeId"]

    # 分区也没了
    assert all(item["id"] != weekend for item in await _partitions(client, token))


# ==================== 权限边界 ====================


async def test_cannot_use_someone_elses_partition(client: AsyncClient, login_as) -> None:
    """分区 ID 是自增可猜的——拿别人的分区 ID 收藏，必须被拒绝。"""
    owner = await _login(client, login_as, "fav-other-owner")
    status, body = await _create_partition(client, owner, "别人的分区")
    assert status == 200, body
    foreign_partition = body["data"]["id"]

    user = await _login(client, login_as, "fav-other-user")
    data = await _space_with_recipe(client, user, "fav-other-user", name="宫保鸡丁")

    response = await client.post(
        f"/api/v1/favorites/{data['recipeId']}",
        json={"partition_id": foreign_partition},
        headers=_auth(user),
    )
    assert response.status_code == 404, response.text

    # 拿别人的分区 ID 来**查**列表也一样拒绝
    listing = await client.get(
        "/api/v1/favorites", params={"partition_id": foreign_partition}, headers=_auth(user)
    )
    assert listing.status_code == 404, listing.text


async def test_cannot_favorite_recipe_in_a_space_you_cannot_see(
    client: AsyncClient, login_as
) -> None:
    """看不到的菜就收不了。

    非成员访问菜谱类接口在本项目里统一返回 403「你不是这个家庭组的成员」
    （ensure_member 的既有行为，所有菜谱接口一致），这里保持同一约定，
    不为收藏单独发明一种返回。
    """
    owner = await _login(client, login_as, "fav-stranger-owner")
    data = await _space_with_recipe(client, owner, "fav-stranger-owner", name="别人家的菜")

    outsider = await _login(client, login_as, "fav-stranger")
    response = await client.post(
        f"/api/v1/favorites/{data['recipeId']}", json={}, headers=_auth(outsider)
    )
    assert response.status_code == 403, response.text

    # recipe-ids 同理：非成员查某个家庭组里自己收藏了哪些菜，同样 403
    ids = await client.get(
        "/api/v1/favorites/recipe-ids",
        params={"space_id": data["spaceId"]},
        headers=_auth(outsider),
    )
    assert ids.status_code == 403, ids.text


async def test_favorite_of_missing_recipe_returns_404(client: AsyncClient, login_as) -> None:
    """菜谱 ID 不存在时返回 404，而不是 500 或假装收藏成功。"""
    token = await _login(client, login_as, "fav-missing")
    response = await client.post("/api/v1/favorites/99999999", json={}, headers=_auth(token))
    assert response.status_code == 404, response.text


async def test_favorites_require_login(client: AsyncClient, login_as) -> None:
    """不带令牌访问收藏相关接口一律 401。"""
    token = await _login(client, login_as, "fav-anon")
    data = await _space_with_recipe(client, token, "fav-anon")

    assert (await client.get("/api/v1/favorites/partitions")).status_code == 401
    assert (
        await client.post("/api/v1/favorites/partitions", json={"name": "x"})
    ).status_code == 401
    assert (await client.get("/api/v1/favorites")).status_code == 401
    assert (
        await client.post(f"/api/v1/favorites/{data['recipeId']}", json={})
    ).status_code == 401
    assert (await client.delete(f"/api/v1/favorites/{data['recipeId']}")).status_code == 401


async def test_recipe_ids_marks_only_favorited(client: AsyncClient, login_as) -> None:
    """recipe-ids 只返回真正收藏过的菜——菜单页靠它决定哪颗星是亮的。"""
    token = await _login(client, login_as, "fav-ids")
    data = await _space_with_recipe(client, token, "fav-ids", name="鱼香肉丝")

    # 没收藏时是空的
    before = await client.get(
        "/api/v1/favorites/recipe-ids",
        params={"space_id": data["spaceId"]},
        headers=_auth(token),
    )
    assert before.status_code == 200, before.text
    assert before.json()["data"] == []

    # 收藏之后只返回这一道
    response = await client.post(
        f"/api/v1/favorites/{data['recipeId']}", json={}, headers=_auth(token)
    )
    assert response.status_code == 200, response.text

    after = await client.get(
        "/api/v1/favorites/recipe-ids",
        params={"space_id": data["spaceId"]},
        headers=_auth(token),
    )
    assert after.json()["data"] == [data["recipeId"]]
