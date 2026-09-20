"""AI 调用配额：每个用户每天最多调多少次对话模型。

═══════════════════════════════════════════════════════════════════════
⭐ 为什么需要它

   AI 页面是项目里**唯一"用户每按一次都可能花钱"**的入口——
   每轮对话都要调一次 qwen-plus，按 token 计费。

   正常使用一天记三顿饭用不了 10 次，但接口是公开的，
   写个脚本循环调就能把额度跑光。所以要有上限。

⭐ 为什么用 Redis 而不是查数据库

   每次对话前都要检查一次，是**高频读 + 高频写**：
     · 查库：还要走连接池、还要 commit，每次对话多一次 DB 往返
     · Redis：`INCR` 是原子操作，微秒级，天然并发安全

   更重要的是 **`EXPIRE` 帮我们实现了"每天重置"**：
   给 key 设到当天 24 点过期，第二天 key 自动消失、计数从 0 开始。
   不用写定时任务去清理昨天的计数。

⭐ key 设计

   `fm:ai:quota:{user_id}:{yyyy-mm-dd}`

   · `fm:` 前缀——本机 Redis 是**你自己的原生 Redis**，
     但同一个实例上未来可能挂别的项目，加前缀避免撞名
   · `{user_id}` —— 用户私有域（和 calorie_logs 一样按 user 隔离）
   · `{yyyy-mm-dd}` —— 日期写进 key 而不是只靠 TTL，
     好处是**可以回看历史**（排查"这人昨天用了多少次"），
     而且跨天边界不会因为 TTL 的秒级误差算错

⭐ 容错原则（关键）

   **Redis 挂了要放行，不能挡住用户。**
   配额是"成本保护"，不是"安全边界"。
   为了限流把正常用户挡在门外，是比超支更严重的问题。
═══════════════════════════════════════════════════════════════════════
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.core.config import settings
from app.core.redis_client import get_client
from app.core.response import CODE_BUSINESS
from app.core.exceptions import BusinessError

logger = logging.getLogger(__name__)

_KEY_PREFIX = "fm:ai:quota:"
#: key 存活上限（秒）。写 2 天是为了跨天留一点余量做排查，
#: 实际重置靠"日期进 key"而不是靠它过期。
_KEY_TTL = 60 * 60 * 48


@dataclass(frozen=True)
class QuotaStatus:
    """当前配额状态。"""

    #: 今天已用次数
    used: int
    #: 今天上限
    limit: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def _today_key(user_id: int, today: date | None = None) -> str:
    day = (today or date.today()).isoformat()
    return f"{_KEY_PREFIX}{user_id}:{day}"


def _seconds_until_tomorrow() -> int:
    """距离明天 0 点还有几秒。给 EXPIRE 用，保证 key 活到自然日结束。"""
    now = datetime.now()
    tomorrow = datetime.combine(now.date() + timedelta(days=1), time.min)
    return max(60, int((tomorrow - now).total_seconds()))


def get_status(user_id: int) -> QuotaStatus:
    """查当前用量（不消耗次数）。给"还剩几次"这类展示用。"""
    limit = settings.max_ai_calls_per_day
    client = get_client()
    if client is None or not settings.ai_quota_enabled:
        # Redis 不可用 / 配额关闭 → 报"满额"，业务照常放行
        return QuotaStatus(used=0, limit=limit)

    try:
        raw = client.get(_today_key(user_id))
        used = int(raw) if raw else 0
    except Exception as exc:
        logger.warning("读取 AI 配额失败（按未使用处理）：%s", exc)
        return QuotaStatus(used=0, limit=limit)

    return QuotaStatus(used=used, limit=limit)


def consume(user_id: int) -> QuotaStatus:
    """消耗一次配额并返回消耗后的状态；超限抛 BusinessError。

    ⭐ **这是唯一的写入口**——"检查 + 计数"必须在一次原子操作里完成。
       如果先 get 再 set，两个并发请求可能都读到 49、都放行，
       实际用了 51 次。`INCR` 返回的就是自增后的值，天然没有这个竞态。

    ⚠️ 计数时机：**在调模型之前**消耗。
       这样"模型调用失败"也算用掉一次——看起来有点亏，但安全：
       否则失败重试可以被无限利用绕过配额。
       而且真实情况里模型调用很少失败（失败会抛 BusinessError 给用户看到）。
    """
    limit = settings.max_ai_calls_per_day

    client = get_client()
    if client is None or not settings.ai_quota_enabled:
        # ⚠️ 容错：Redis 不可用 / 开关关闭 → **放行**
        #    理由见文件头"容错原则"：配额是成本保护，不是安全边界，
        #    为了限流把用户挡在门外比超支更糟。
        return QuotaStatus(used=0, limit=limit)

    try:
        key = _today_key(user_id)
        used = client.incr(key)
        # 第一次自增时才设过期，避免每次请求都刷 TTL（虽然也不贵）
        if used == 1:
            client.expire(key, _seconds_until_tomorrow())
    except Exception as exc:
        logger.warning("AI 配额计数失败（放行本次）：%s", exc)
        return QuotaStatus(used=0, limit=limit)

    if used > limit:
        logger.info("AI 配额已用尽 | user_id=%s | used=%s | limit=%s", user_id, used, limit)
        raise BusinessError(
            f"今天的 AI 对话次数用完了（每天 {limit} 次），明天再聊吧",
            code=CODE_BUSINESS,
        )

    return QuotaStatus(used=used, limit=limit)
