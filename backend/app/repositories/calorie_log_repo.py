"""热量记录的数据访问。

约定同其它 repository：只管查和存，不写业务规则，也不调用 commit。
所有查询都带 user_id 过滤，保证私有域隔离。
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_profile import CalorieLog


class CalorieLogRepository:
    """热量记录的查询与写入。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_user(
        self,
        user_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[CalorieLog]:
        """列出某用户的热量记录，按日期倒序。可按日期区间过滤。"""
        stmt = select(CalorieLog).where(CalorieLog.user_id == user_id)
        if date_from is not None:
            stmt = stmt.where(CalorieLog.eaten_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(CalorieLog.eaten_at <= date_to)
        stmt = stmt.order_by(CalorieLog.eaten_at.desc(), CalorieLog.id.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, user_id: int, data: dict) -> CalorieLog:
        """新增一条记录。data 的键就是模型字段名。"""
        log = CalorieLog(user_id=user_id, **data)
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_owned(self, user_id: int, log_id: int) -> CalorieLog | None:
        """按 ID 取记录，同时校验归属：不是你的就当不存在，删除前用。"""
        stmt = select(CalorieLog).where(
            CalorieLog.id == log_id,
            CalorieLog.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, log: CalorieLog) -> None:
        """删除一条记录（先校验归属）。"""
        await self.session.delete(log)
        await self.session.flush()
