"""数据访问层（Repository）：只负责和数据库打交道。

这一层不写业务规则，只做"查/存"。
好处是：将来如果换数据库、或者给查询加缓存，改动都集中在这里，不影响业务逻辑。
"""

from app.repositories.user_repo import UserRepository

__all__ = ["UserRepository"]
