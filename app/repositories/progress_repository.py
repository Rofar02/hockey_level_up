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
        self,
        user_id: uuid.UUID,
        stat_type: TargetStat,
        value: float,
        now: datetime,
        reason: str,
    ) -> None:
        """Overwrite current_value (assessment baseline), unlike stat_consumer's additive
        upsert -- and log the overwrite to StatHistory so the jump is attributed to the
        assessment itself rather than silently absorbed into the next quest_completed row."""
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
        self._session.add(
            StatHistory(user_id=user_id, stat_type=stat_type, value=value, reason=reason)
        )

    async def ensure_stat_exists(
        self,
        user_id: uuid.UUID,
        stat_type: TargetStat,
        value: float,
        now: datetime,
        reason: str,
    ) -> bool:
        """Insert a baseline row only if one doesn't already exist -- unlike
        set_stat_value above (an unconditional upsert), this never
        overwrites a value that's already there. For stats a user hasn't
        "earned" yet through their own dedicated flow (e.g. on-ice stats
        for someone who's only done the off-ice assessment): safe to call
        on every off-ice assessment/retake, since after the first insert it
        becomes a no-op and can never clobber a real on-ice test result
        recorded via set_stat_value in the meantime. Returns whether a row
        was actually inserted (only then is the seed logged to
        StatHistory -- a no-op insert has nothing new to attribute).
        """
        stmt = (
            pg_insert(UserStat)
            .values(user_id=user_id, stat_type=stat_type, current_value=value, last_updated_at=now)
            .on_conflict_do_nothing(constraint="uq_user_stats_user_stat_type")
            .returning(UserStat.id)
        )
        result = await self._session.execute(stmt)
        inserted = result.scalar_one_or_none() is not None
        if inserted:
            self._session.add(
                StatHistory(user_id=user_id, stat_type=stat_type, value=value, reason=reason)
            )
        return inserted
