"""Redis 连接（缓存 + 计数共用）。

⭐ 为什么单独一个文件？
   因为是**两个模块共用**的连接（营养缓存在 services/nutrition_service.py，
   配额计数在 services/ai_quota_service.py）。连接池只有一个才合理——
   各建各的会出现"两个池、两份连接"，Redis 侧也会看到多余的 client。

⭐ 为什么用**同步**的 redis 客户端？
   项目其余部分全是 async，看起来该用 `redis.asyncio`。但这里有两个现实原因：

   1) **Redis 就是本机 / 内网**，一次 PING 通常 < 1ms。
      `redis.asyncio` 的每次 await 都要过一遍事件循环调度，开销反而可能更大。
   2) **部署形态简单**——单实例、非集群。同步客户端足够。

   ⚠️ 但**单次调用必须极短**（就是 GET / SET / INCR，没有慢查询）。
      如果哪天要放到公网 Redis 或做大 key 扫描，就该换成 redis.asyncio，
      并且要在 async 函数里用 `await asyncio.to_thread(...)` 包一层避免阻塞事件循环。

⭐ 容错原则：**Redis 挂了不能影响业务。**
   缓存拿不到 → 回源查；配额记不上 → 放行（宁可少限流，不可挡住用户）。
   所以下面所有函数都 catch 异常并返回"中性值"，绝不抛给上层。
"""

import logging

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

#: 连接池。None = 还没初始化（或初始化失败过，可重试）。
_pool: redis.ConnectionPool | None = None
#: 初始化失败的标记。失败一次后不再反复尝试建池，避免每次请求都卡超时。
_init_failed = False


def get_client() -> redis.Redis | None:
    """取 Redis 客户端。连不上就返回 None（调用方自行降级）。"""
    global _pool, _init_failed

    if not settings.redis_enabled:
        return None
    if _init_failed:
        return None

    if _pool is None:
        try:
            _pool = redis.ConnectionPool.from_url(
                settings.redis_url,
                decode_responses=True,  # 直接返回 str，省得到处 .decode()
                socket_connect_timeout=2.0,  # 连不上时快速失败，不拖慢接口
                socket_timeout=2.0,
                max_connections=16,
            )
        except Exception as exc:
            logger.warning("Redis 连接池创建失败，缓存与配额将不生效：%s", exc)
            _init_failed = True
            return None

    return redis.Redis(connection_pool=_pool)


def ping() -> bool:
    """探活。给健康检查用。"""
    client = get_client()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except Exception as exc:
        logger.warning("Redis PING 失败：%s", exc)
        return False


def reset_state() -> None:
    """重置连接状态（测试用）。

    断开旧池并清掉失败标记——测试里会 mock 掉 redis 相关函数，
    每个用例之间必须干净，否则上一个用例的"连接失败"标记会传染下一个。
    """
    global _pool, _init_failed
    if _pool is not None:
        try:
            _pool.disconnect()
        except Exception:
            pass
    _pool = None
    _init_failed = False
