import uuid

from sqlalchemy import select
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
