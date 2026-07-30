import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import TargetStat
from app.models.progress import StatHistory, TrainingStreak, UserStat


class ProgressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_user_stats(self, user_id: uuid.UUID) -> list[UserStat]:
        result = await self._session.execute(
            select(UserStat).where(UserStat.user_id == user_id).order_by(UserStat.stat_type)
        )
        return list(result.scalars().all())

    async def list_stat_history(
        self, user_id: uuid.UUID, stat_type: TargetStat
    ) -> list[StatHistory]:
        result = await self._session.execute(
            select(StatHistory)
            .where(StatHistory.user_id == user_id, StatHistory.stat_type == stat_type)
            .order_by(StatHistory.recorded_at)
        )
        return list(result.scalars().all())

    async def get_streak(self, user_id: uuid.UUID) -> TrainingStreak | None:
        result = await self._session.execute(
            select(TrainingStreak).where(TrainingStreak.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_stat(self, user_id: uuid.UUID, stat_type: TargetStat) -> UserStat | None:
        result = await self._session.execute(
            select(UserStat).where(UserStat.user_id == user_id, UserStat.stat_type == stat_type)
        )
        return result.scalar_one_or_none()

    async def set_stat_value(
        self, user_id: uuid.UUID, stat_type: TargetStat, value: float, now: datetime
    ) -> None:
        """Overwrite current_value (assessment baseline), unlike stat_consumer's additive upsert."""
        stmt = pg_insert(UserStat).values(
            user_id=user_id, stat_type=stat_type, current_value=value, last_updated_at=now
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_stats_user_stat_type",
            set_={
                "current_value": stmt.excluded.current_value,
                "last_updated_at": stmt.excluded.last_updated_at,
            },
        )
        await self._session.execute(stmt)
