"""pytest 公共夹具（fixture）。

夹具就是"测试开始前准备好的东西"。这里准备三样：
    1. 一个测试客户端（直接调应用内部，不走真实网络端口）；
    2. 一个"注册一个全新用户并登录"的工厂，用来造出多个不同用户，
       从而测试多用户协作与权限边界；
    3. 一个**会话结束时自动清理测试数据**的收尾夹具（见下方 _cleanup_test_data）。

为什么登录工厂要放在这里、而不是每个测试文件各写一份？
    因为"怎么造出一个用户"这件事是可能变的（将来也许会多一种登录方式）。
    放在公共位置只改一处；各写一份的话，改的时候一定会漏，
    然后出现"某个测试文件莫名其妙全挂"的情况。

⚠️ 关于测试数据会落进开发库这件事（历史遗留，已用收尾清理缓解）：
    测试连的是 .env 里配置的开发库，数据会真的写进去。
    之前每跑一次就留下上百个临时用户（2026-09-20 实测：一次全量测试
    留下 220 个用户 / 144 个家庭组），日积月累把库搞得没法看。
    现在改为**整轮测试结束后自动按用户名模式清理**——
    彻底的做法是搞一个独立的测试库，那是更大的一件事，先这样。
"""

# 必须在导入任何会创建事件循环的东西之前完成策略设置，
# 否则 Windows 上会拿到 ProactorEventLoop，导致数据库连接直接失败。
from app.core.event_loop import apply_selector_loop_policy

apply_selector_loop_policy()

import asyncio  # noqa: E402
import re  # noqa: E402
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator  # noqa: E402
from uuid import uuid4  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402

# 测试账号统一使用这个密码。抽成常量，将来密码规则变了只改这一处。
TEST_PASSWORD = "TestPass123"

# 用户名上限是 20 位（见 app/models/user.py）。
# 这里把"可读前缀"截断到 10 位，剩下的位置留给 1 个下划线 + 8 位随机后缀，
# 保证自动生成的名字一定是合法的、且不同测试之间不会撞名。
_PREFIX_MAX_LENGTH = 10
_RANDOM_SUFFIX_LENGTH = 8

# 真人账号的 id —— 清理时**必须避开**，绝不能误删。
# 见项目长期记忆：库里只有 zjy(1602) 和 zjy1(1961) 是真人，
# 其余都是 pytest 残留（这句以前是"人肉记住"的，现在让代码替我们记住）。
_KEEP_USER_IDS = (1602, 1961)


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """直连应用的测试客户端。

    使用 ASGITransport 不经过真实网络端口，直接调用应用内部，
    测试更快、也不会因为端口被占用而失败。

    ⚠️ 这里连接的是 .env 里配置的开发数据库，测试数据会真的落进 family_menu 库。
       清理由会话级的 _cleanup_test_data 在整轮测试结束后统一做。
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def _max_user_id() -> int:
    """取当前最大的用户 id（0 表示表是空的）。

    独立成一个同步函数、内部自己开事件循环，原因见 _cleanup_test_data 的说明
    （session 级夹具拿不到 pytest-asyncio 的函数级事件循环）。
    """

    async def _query() -> int:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT coalesce(max(id), 0) FROM users"))
            return int(result.scalar() or 0)

    return asyncio.run(_query())


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_data() -> Generator[None, None, None]:
    """整轮测试跑完后，删掉本次测试造出来的数据（自动生效，不用手动调）。

    为什么要 scope="session" + autouse？
        - 想"跑完一批测试后统一清一次"，而不是每个用例清一次（那样又慢又乱）；
        - autouse 保证**所有**测试文件都受保护，而不是只有 import 了它的那个。

    ⚠️ 为什么是**同步** fixture、内部自己 asyncio.run？
        pytest-asyncio 提供的事件循环 fixture 是**函数级**的，
        session 级的异步 fixture 会报
        `ScopeMismatch: You tried to access the function scoped fixture
         _function_scoped_runner with a session scoped request object`。
        所以这里用同步夹具，在收尾时**自己起一个短命的事件循环**跑清理——
        清理和测试用的本来就不是同一批连接，换个循环没有副作用。

    ⚠️ 怎么判断"哪些数据是测试造的"？两条条件取并集：
        ① **id 大于"测试开始时的最大用户 id"** —— 本轮测试新建的，最准确；
        ② **用户名匹配测试命名模式** —— 用来兜住以前遗留的残留。
        ⭐ 加了 ① 是因为踩过一个坑：有些用例会造**没有用户名**的用户
           （昵称「小家用户」），只按用户名模式根本抓不到，会一直累积。

    ⚠️ 两条安全底线：
        1. **_KEEP_USER_IDS 里的真人 id 无条件排除**（即使它们碰巧匹配）；
        2. 真人用户 id 都在①的阈值之前、用户名也不匹配②，双重不会命中。

    删除顺序：从"叶子"表往"根"表删（关联表 → 主表 → users），
    否则会撞外键约束。
    """
    # ---- 测试开始前：记下当前最大 id，作为"是不是本轮造的"的分界线 ----
    start_max_id = _max_user_id()

    yield

    # 测试用户名的模式：`<prefix>_<8位hex>`。
    # 例如 creator_5fd48fbc、member_cat_a1b2c3d4、ord_spice__b4c9785c。
    #
    # ⚠️ 前缀部分必须允许下划线！——这里踩过一次：
    #    一开始写成 `^[A-Za-z0-9]+_[0-9a-f]{8}$`（前缀不含下划线），
    #    结果只匹配到 4 个用户（因为大量前缀本身就是 `member_cat`、`quota_leav`、
    #    `ord_spice` 这种带下划线的），残留清不掉。
    #    实测：旧写法匹配 4 条，加上 `_` 后匹配 210 条，差的正好是要清的那些。
    #
    # ⚠️ 真人 `zjy` / `zjy1` 不含下划线、也不以 _8位hex 结尾，绝不会命中
    #    （实测未匹配的恰好只有这两个）。
    pattern = r"^[A-Za-z0-9_]+_[0-9a-f]{8}$"

    # 用原生 SQL 逐层删（跨多张表批量删，走 ORM 反而绕，还要处理对象状态）。
    # 全部塞进一条 CTE 语句里，用事务保证要么全成、要么全不动。
    cleanup_sql = text(
        f"""
        WITH test_uids AS (
            SELECT id FROM users
            WHERE id NOT IN {_KEEP_USER_IDS}
              AND (id > {start_max_id} OR username ~ '{pattern}')
        ),
        doomed_orders AS (
            SELECT id FROM dish_orders WHERE created_by IN (SELECT id FROM test_uids)
        ),
        doomed_spaces AS (
            SELECT DISTINCT space_id FROM space_members
            WHERE user_id IN (SELECT id FROM test_uids)
        ),
        del_order_items AS (
            DELETE FROM dish_order_items
            WHERE order_id IN (SELECT id FROM doomed_orders) RETURNING 1
        ),
        del_favorites AS (
            DELETE FROM recipe_favorites
            WHERE user_id IN (SELECT id FROM test_uids) RETURNING 1
        ),
        del_partitions AS (
            DELETE FROM favorite_partitions
            WHERE user_id IN (SELECT id FROM test_uids) RETURNING 1
        ),
        del_calories AS (
            DELETE FROM calorie_logs
            WHERE user_id IN (SELECT id FROM test_uids) RETURNING 1
        ),
        del_chats AS (
            DELETE FROM ai_chat_messages
            WHERE user_id IN (SELECT id FROM test_uids) RETURNING 1
        ),
        del_profiles AS (
            DELETE FROM user_profiles
            WHERE user_id IN (SELECT id FROM test_uids) RETURNING 1
        ),
        del_identities AS (
            DELETE FROM user_identities
            WHERE user_id IN (SELECT id FROM test_uids) RETURNING 1
        ),
        del_fridge AS (
            DELETE FROM fridge_items
            WHERE created_by IN (SELECT id FROM test_uids) RETURNING 1
        ),
        del_orders AS (
            DELETE FROM dish_orders
            WHERE created_by IN (SELECT id FROM test_uids) RETURNING 1
        ),
        del_recipes AS (
            DELETE FROM recipes
            WHERE created_by IN (SELECT id FROM test_uids) RETURNING 1
        ),
        del_members AS (
            DELETE FROM space_members
            WHERE user_id IN (SELECT id FROM test_uids) RETURNING 1
        ),
        del_categories AS (
            DELETE FROM recipe_categories
            WHERE space_id IN (SELECT space_id FROM doomed_spaces) RETURNING 1
        ),
        del_spaces AS (
            DELETE FROM spaces
            WHERE id IN (SELECT space_id FROM doomed_spaces)
              AND id NOT IN (
                  SELECT DISTINCT space_id FROM space_members
                  WHERE user_id NOT IN (SELECT id FROM test_uids)
              )
            RETURNING 1
        ),
        del_users AS (
            DELETE FROM users WHERE id IN (SELECT id FROM test_uids) RETURNING 1
        )
        SELECT
            (SELECT count(*) FROM del_users) AS users,
            (SELECT count(*) FROM del_spaces) AS spaces,
            (SELECT count(*) FROM del_recipes) AS recipes,
            (SELECT count(*) FROM del_categories) AS categories
        """
    )

    async def _run() -> None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(cleanup_sql)
            await session.commit()
            users, spaces, recipes, categories = result.one()
        if users or spaces or recipes or categories:
            print(
                f"\n[pytest] 已清理测试残留："
                f"用户 {users} / 家庭组 {spaces} / 菜谱 {recipes} / 分类 {categories}"
            )

    try:
        asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 —— 清理失败不该让测试结果变红
        # 清理是"收尾工作"，失败了只提示，不改变测试结论
        # （否则会出现"测试全过但退出码非 0"这种最让人困惑的情况）。
        print(f"\n[pytest] 测试数据清理失败（不影响测试结论）：{type(exc).__name__}: {exc}")


@pytest_asyncio.fixture
async def login_as(
    client: AsyncClient,
) -> Callable[[str], Awaitable[tuple[str, int]]]:
    """返回一个"注册并登录一个全新用户"的函数，调用后得到 (访问令牌, 用户 ID)。

    为什么改成"真去注册"，而不是像以前那样靠 AUTH_DEV_MODE 伪造一个 openid？
        伪造出来的用户永远绕过了注册链路，于是注册那套最该被测的逻辑
        ——用户名唯一性、格式校验、密码哈希——在整套测试里一次都没跑过。
        改成真注册之后，各个测试文件里的多用户场景顺带也覆盖了注册接口。

    参数 prefix 只是让用户名好认：排查测试残留数据时，一眼能看出是哪条用例造的。
    前缀里可能带短横线（例如 "case-owner"），而用户名只允许字母数字下划线，所以要替换掉。

    ⭐ 命名格式 `{prefix}_{8位hex}` 同时是**清理夹具的识别依据**（见 _cleanup_test_data），
       所以这个后缀长度不能随便改——改了会让旧数据清不掉。
    """

    async def _register(prefix: str) -> tuple[str, int]:
        safe_prefix = re.sub(r"[^A-Za-z0-9_]", "_", prefix)[:_PREFIX_MAX_LENGTH]
        username = f"{safe_prefix}_{uuid4().hex[:_RANDOM_SUFFIX_LENGTH]}"

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "password": TEST_PASSWORD,
                # 注册要求二次确认（防用户打错），所以两个字段都要给
                "password_confirm": TEST_PASSWORD,
            },
        )
        assert response.status_code == 200, response.text

        data = response.json()["data"]
        return data["token"], data["user"]["id"]

    return _register
