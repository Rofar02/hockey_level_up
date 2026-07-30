import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import TargetStat
from app.models.progress import StatHistory, TrainingStreak, UserStat
from app.repositories.progress_repository import ProgressRepository


class ProgressService:
    def __init__(self, session: AsyncSession) -> None:
        self._progress = ProgressRepository(session)

    async def list_user_stats(self, user_id: uuid.UUID) -> list[UserStat]:
        return await self._progress.list_user_stats(user_id)

    async def list_stat_history(
        self, user_id: uuid.UUID, stat_type: TargetStat
    ) -> list[StatHistory]:
        return await self._progress.list_stat_history(user_id, stat_type)

    async def get_streak(self, user_id: uuid.UUID) -> TrainingStreak:
        streak = await self._progress.get_streak(user_id)
        if streak is None:
            return TrainingStreak(
                user_id=user_id, current_streak=0, longest_streak=0, last_activity_date=None
            )
        return streak
