"""家庭组额度测试：一个人能建几个、能加几个。

业务规则（用户定的）：
    一个人最多有 4 个家庭组 —— **最多创建 2 个、最多加入 2 个**。
    创建满了提示"您创建的家庭组数量已达上限"；
    加入满了提示"您加入的家庭组数量已达上限"。

覆盖六类行为：
    1. 额度接口返回默认的 2/2；
    2. 创建满额后被拒，提示里带出上限数字；
    3. 加入满额后被拒，提示里带出上限数字；
    4. **口径**：自己创建的家不算进"我加入的"额度（这是最容易算错的一处）；
    5. 释放额度后又可以建/可以加（解散、退出）；
    6. **额度可配置**：改配置立即生效——证明没有写死在代码里，将来接会员能接得上。
"""

from httpx import AsyncClient

from app.core.config import settings


def _auth(token: str) -> dict[str, str]:
    """构造带令牌的请求头。"""
    return {"Authorization": f"Bearer {token}"}


async def _quota(client: AsyncClient, token: str) -> dict:
    """读额度。"""
    response = await client.get("/api/v1/spaces/quota", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _create_space(client: AsyncClient, token: str, name: str) -> tuple[int, str]:
    """建一个家庭组，返回 (状态码, 响应文本)。"""
    response = await client.post("/api/v1/spaces", json={"name": name}, headers=_auth(token))
    return response.status_code, response.text


async def _create_space_ok(client: AsyncClient, token: str, name: str) -> dict:
    """建一个家庭组并断言成功。"""
    response = await client.post("/api/v1/spaces", json={"name": name}, headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _join(client: AsyncClient, token: str, invite_code: str) -> tuple[int, dict]:
    """用邀请码加入，返回 (状态码, 响应体)。"""
    response = await client.post(
        "/api/v1/spaces/join", json={"invite_code": invite_code}, headers=_auth(token)
    )
    return response.status_code, response.json()


async def _invite_code(client: AsyncClient, owner_token: str, space_id: int) -> str:
    """从创建人的列表里取邀请码。"""
    listed = await client.get("/api/v1/spaces", headers=_auth(owner_token))
    assert listed.status_code == 200, listed.text
    for item in listed.json()["data"]:
        if int(item["id"]) == int(space_id):
            assert item["invite_code"], "创建人应该能看到自己的邀请码"
            return item["invite_code"]
    raise AssertionError("列表里没找到这个家庭组")


# ==================== 额度接口 ====================


async def test_quota_returns_defaults(client: AsyncClient, login_as) -> None:
    """新用户的额度应该是配置里的默认值，用量从 0 开始。

    顺带守住路由顺序：如果 /spaces/quota 被 /spaces/{space_id} 抢走，
    这里会拿到 422 而不是这几个字段——所以这条也在盯那个坑。
    """
    token, _ = await login_as("quota-default")
    quota = await _quota(client, token)

    assert quota == {
        "max_owned": settings.max_owned_spaces,
        "max_joined": settings.max_joined_spaces,
        "owned": 0,
        "joined": 0,
    }


async def test_quota_requires_login(client: AsyncClient) -> None:
    """不带令牌读额度返回 401。"""
    response = await client.get("/api/v1/spaces/quota")
    assert response.status_code == 401


async def test_quota_counts_reflect_usage(client: AsyncClient, login_as) -> None:
    """建一个、加一个之后，用量要分别 +1，而且是分开记的。"""
    owner_token, _ = await login_as("quota-usage-owner")
    space_a = await _create_space_ok(client, owner_token, "额度用量A")

    token, _ = await login_as("quota-usage-user")
    mine = await _create_space_ok(client, token, "我自己建的")
    status, _ = await _join(client, token, await _invite_code(client, owner_token, space_a["id"]))
    assert status == 200

    quota = await _quota(client, token)
    assert quota["owned"] == 1
    assert quota["joined"] == 1

    # 自己建的那个家不能同时算进"我加入的"——否则额度会平白少一个位置
    listed = await client.get("/api/v1/spaces", headers=_auth(token))
    roles = {int(item["id"]): item["my_role"] for item in listed.json()["data"]}
    assert roles[mine["id"]] == "admin"
    assert roles[space_a["id"]] == "member"


# ==================== 创建额度 ====================


async def test_cannot_create_beyond_limit(client: AsyncClient, login_as) -> None:
    """创建满额后再建要被拒绝，提示里要说清上限是多少。"""
    token, _ = await login_as("quota-create-limit")

    for index in range(settings.max_owned_spaces):
        status, text = await _create_space(client, token, f"额度内建的第{index + 1}个")
        assert status == 200, text

    status, text = await _create_space(client, token, "超额的这一个")
    assert status == 400, text
    assert "创建的家庭组数量已达上限" in text
    assert str(settings.max_owned_spaces) in text


async def test_can_create_again_after_dissolve(client: AsyncClient, login_as) -> None:
    """解散一个之后，额度释放，可以再创建。"""
    token, _ = await login_as("quota-create-release")

    spaces = [
        await _create_space_ok(client, token, f"待释放{index}")
        for index in range(settings.max_owned_spaces)
    ]
    assert (await _create_space(client, token, "已经满了"))[0] == 400

    dissolved = await client.delete(f"/api/v1/spaces/{spaces[0]['id']}", headers=_auth(token))
    assert dissolved.status_code == 200, dissolved.text

    status, text = await _create_space(client, token, "释放后新建的")
    assert status == 200, text

    quota = await _quota(client, token)
    assert quota["owned"] == settings.max_owned_spaces


# ==================== 加入额度 ====================


async def test_cannot_join_beyond_limit(client: AsyncClient, login_as) -> None:
    """加入满额后再加要被拒绝，提示里要说清上限是多少。

    这同时也是「被邀请人已满」的提示——
    加入只有"输邀请码"这一个入口，自己找到的码和人家分享的码走的是同一条路。

    注意造数据的方式：**业主自己也有创建额度**，不能让一个业主建 3 个家
    （那样第 3 个就已经被拒了，测试会因为拿不到邀请码而报一个看不懂的错）。
    所以这里用两个业主来凑够"待加入"的家。
    """
    owner_a, _ = await login_as("quota-join-owner-a")
    owner_b, _ = await login_as("quota-join-owner-b")

    codes = []
    for index in range(settings.max_joined_spaces):
        space = await _create_space_ok(client, owner_a, f"待加入A{index}")
        codes.append(await _invite_code(client, owner_a, space["id"]))
    extra = await _create_space_ok(client, owner_b, "待加入B")
    codes.append(await _invite_code(client, owner_b, extra["id"]))

    token, _ = await login_as("quota-join-user")
    for code in codes[: settings.max_joined_spaces]:
        status, body = await _join(client, token, code)
        assert status == 200, body

    status, body = await _join(client, token, codes[settings.max_joined_spaces])
    assert status == 400, body
    assert "加入的家庭组数量已达上限" in body["message"]
    assert str(settings.max_joined_spaces) in body["message"]


async def test_can_join_again_after_leaving(client: AsyncClient, login_as) -> None:
    """退出一个之后，额度释放，可以再加入别的。"""
    owner_a, _ = await login_as("quota-leave-owner-a")
    owner_b, _ = await login_as("quota-leave-owner-b")

    spaces = [
        await _create_space_ok(client, owner_a, f"甲家{index}")
        for index in range(settings.max_joined_spaces)
    ]
    extra = await _create_space_ok(client, owner_b, "乙家")

    token, _ = await login_as("quota-leave-user")
    joined_ids = []
    for space in spaces:
        status, _ = await _join(client, token, await _invite_code(client, owner_a, space["id"]))
        assert status == 200
        joined_ids.append(space["id"])

    extra_code = await _invite_code(client, owner_b, extra["id"])
    assert (await _join(client, token, extra_code))[0] == 400

    # 退出最早加入的那个，腾出位置
    left = await client.post(f"/api/v1/spaces/{joined_ids[0]}/leave", headers=_auth(token))
    assert left.status_code == 200, left.text

    status, body = await _join(client, token, extra_code)
    assert status == 200, body

    quota = await _quota(client, token)
    assert quota["joined"] == settings.max_joined_spaces


# ==================== 额度可配置（不许写死） ====================


async def test_quota_is_configurable_not_hardcoded(
    client: AsyncClient, login_as, monkeypatch
) -> None:
    """把配置调小，限制要立刻跟着变。

    这条是**专门证明"额度没有写死在代码里"**的：
    如果哪天有人图省事把 `2` 直接写进判断，这条测试会立刻红。
    将来接会员，就是让 space_quota_for() 按人返回不同的数字，
    调用方一行都不用动。
    """
    monkeypatch.setattr(settings, "max_owned_spaces", 1)
    monkeypatch.setattr(settings, "max_joined_spaces", 1)

    token, _ = await login_as("quota-configurable")

    quota = await _quota(client, token)
    assert quota["max_owned"] == 1
    assert quota["max_joined"] == 1

    assert (await _create_space(client, token, "第一个"))[0] == 200
    status, text = await _create_space(client, token, "第二个")
    assert status == 400, text
    assert "1 个" in text

    # 额度调小后业主也只能建 1 个，所以第二个"别家"得换一个人来建
    owner_token, _ = await login_as("quota-configurable-owner-a")
    space = await _create_space_ok(client, owner_token, "别人家的")
    code = await _invite_code(client, owner_token, space["id"])

    assert (await _join(client, token, code))[0] == 200

    owner_token_b, _ = await login_as("quota-configurable-owner-b")
    other = await _create_space_ok(client, owner_token_b, "别人家第二个")
    status, body = await _join(client, token, await _invite_code(client, owner_token_b, other["id"]))
    assert status == 400, body
    assert "1 个" in body["message"]
