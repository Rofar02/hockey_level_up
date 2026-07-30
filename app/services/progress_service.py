import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import TargetStat
from app.models.progress import TrainingStreak, UserStat
from app.repositories.progress_repository import ProgressRepository
from app.schemas.progress import StatHistoryRead, UserStatRead
from app.services.stat_service import get_effective_value, get_idle_days, is_decay_active


class ProgressService:
    def __init__(self, session: AsyncSession) -> None:
        self._progress = ProgressRepository(session)

    async def list_user_stats(self, user_id: uuid.UUID) -> list[UserStatRead]:
        stats = await self._progress.list_user_stats(user_id)
        now = datetime.now(timezone.utc)
        return [self._to_stat_read(stat, now) for stat in stats]

    async def list_stat_history(
        self, user_id: uuid.UUID, stat_type: TargetStat
    ) -> list[StatHistoryRead]:
        history = await self._progress.list_stat_history(user_id, stat_type)
        entries = [StatHistoryRead.model_validate(h) for h in history]

        stat = await self._progress.get_user_stat(user_id, stat_type)
        if stat is None:
            return entries

        now = datetime.now(timezone.utc)
        idle_days = get_idle_days(stat, now)
        if not is_decay_active(idle_days):
            return entries

        last_recorded_date = entries[-1].recorded_at.date() if entries else None
        if last_recorded_date == now.date():
            return entries

        # Synthetic, read-time-only point: never written to stat_history.
        entries.append(
            StatHistoryRead(
                stat_type=stat_type,
                value=get_effective_value(stat, now),
                recorded_at=now,
                reason="decay",
            )
        )
        return entries

    async def get_streak(self, user_id: uuid.UUID) -> TrainingStreak:
        streak = await self._progress.get_streak(user_id)
        if streak is None:
            return TrainingStreak(
                user_id=user_id, current_streak=0, longest_streak=0, last_activity_date=None
            )
        return streak

    @staticmethod
    def _to_stat_read(stat: UserStat, now: datetime) -> UserStatRead:
        effective_value = get_effective_value(stat, now)
        idle_days = get_idle_days(stat, now)
        return UserStatRead(
            stat_type=stat.stat_type,
            current_value=stat.current_value,
            effective_value=effective_value,
            trend="up" if effective_value == stat.current_value else "down",
            idle_days=idle_days,
            decay_active=is_decay_active(idle_days),
            last_updated_at=stat.last_updated_at,
        )
