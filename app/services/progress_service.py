import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.expected_baseline import get_expected_baseline
from app.models.exercise import TargetStat
from app.models.progress import TrainingStreak, UserStat
from app.models.user import User
from app.repositories.progress_repository import ProgressRepository
from app.schemas.progress import StatHistoryPointRead, StatHistoryRead, UserStatRead
from app.services.stat_service import get_effective_value, get_idle_days, is_decay_active

# All 4 stats are always included in rating_excess, even ones the user has
# never trained (excess is then 0 - baseline, i.e. fully negative).
RATED_STAT_TYPES = (
    TargetStat.STRENGTH,
    TargetStat.AGILITY,
    TargetStat.ENDURANCE,
    TargetStat.INTELLECT,
)


def _stat_excess(stat_type: TargetStat, user: User, stat: UserStat | None, now: datetime) -> float:
    effective_value = get_effective_value(stat, now) if stat is not None else 0.0
    baseline = get_expected_baseline(stat_type, user.age, user.years_of_experience)
    return effective_value - baseline


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
        if not is_decay_active(idle_days, stat_type):
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

    async def get_stats_history(
        self, user_id: uuid.UUID, stat_type: TargetStat | None, days: int
    ) -> list[StatHistoryPointRead] | dict[TargetStat, list[StatHistoryPointRead]]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        if stat_type is not None:
            return await self._history_points(user_id, stat_type, since)
        # No stat_type -- every stat's window in one response, grouped by
        # type, rather than making the caller issue one request per stat.
        return {stat: await self._history_points(user_id, stat, since) for stat in TargetStat}

    async def _history_points(
        self, user_id: uuid.UUID, stat_type: TargetStat, since: datetime
    ) -> list[StatHistoryPointRead]:
        history = await self._progress.list_stat_history_since(user_id, stat_type, since)
        return [StatHistoryPointRead(date=entry.recorded_at.date(), value=entry.value) for entry in history]

    async def get_stat_excess(self, stat_type: TargetStat, user: User) -> float:
        if user.age is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="age is required to compute a competitive rating",
            )
        stat = await self._progress.get_user_stat(user.id, stat_type)
        return _stat_excess(stat_type, user, stat, datetime.now(timezone.utc))

    async def get_rating_excess(self, user: User) -> float:
        if user.age is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="age is required to compute a competitive rating",
            )
        stats = await self._progress.list_user_stats(user.id)
        stats_by_type = {stat.stat_type: stat for stat in stats}
        now = datetime.now(timezone.utc)
        excesses = [
            _stat_excess(stat_type, user, stats_by_type.get(stat_type), now)
            for stat_type in RATED_STAT_TYPES
        ]
        return round(sum(excesses) / len(excesses), 1)

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
            decay_active=is_decay_active(idle_days, stat.stat_type),
            last_updated_at=stat.last_updated_at,
        )
