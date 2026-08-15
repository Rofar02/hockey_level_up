import uuid
from datetime import date

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingBlock, TrainingSession, WeeklyPlan

# Mirrors streak_service.TRAINING_SESSION_TYPES -- same "what counts as a
# real training day" rule (GAME is light activation, not a workout; REST is
# nothing at all), duplicated here rather than importing a service module
# into a repository. Same deliberate, acknowledged duplication as
# _has_completed_block/training_party_service.py's _day_plan_has_completed_block.
_TRAINING_SESSION_TYPES = (DaySessionType.ON_ICE, DaySessionType.OFF_ICE)


class TrainingBlockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_for_user(self, user_id: uuid.UUID) -> TrainingBlock | None:
        """The user's current block: the row with the highest block_number."""
        result = await self._session.execute(
            select(TrainingBlock)
            .where(TrainingBlock.user_id == user_id)
            .order_by(TrainingBlock.block_number.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def create(self, block: TrainingBlock) -> TrainingBlock:
        self._session.add(block)
        await self._session.flush()
        return block

    async def get_by_id(self, block_id: uuid.UUID) -> TrainingBlock | None:
        return await self._session.get(TrainingBlock, block_id)

    async def count_completed_real_sessions(self, block_id: uuid.UUID, since: date) -> int:
        """How many on/off-ice TrainingSessions -- every one of their
        SessionBlocks completed, and at least one block exists at all (an
        empty session, e.g. from a catalog gap, isn't "done") -- were
        scheduled under `block_id` on or after `since`.

        Scoped by DayPlan.date, not by which BlockPhase a session happened
        to be assembled under: `since` is always the current phase's
        phase_started_at, so sessions from a since-elapsed earlier phase
        (before the date cutoff) are correctly excluded from this count
        without needing to record "which phase" on every session.
        """
        has_any_block = exists().where(SessionBlock.session_id == TrainingSession.id)
        has_incomplete_block = exists().where(
            SessionBlock.session_id == TrainingSession.id, SessionBlock.completed_at.is_(None)
        )
        result = await self._session.execute(
            select(func.count(TrainingSession.id))
            .select_from(TrainingSession)
            .join(DayPlan, TrainingSession.day_plan_id == DayPlan.id)
            .join(WeeklyPlan, DayPlan.weekly_plan_id == WeeklyPlan.id)
            .where(
                WeeklyPlan.training_block_id == block_id,
                DayPlan.date >= since,
                DayPlan.session_type.in_(_TRAINING_SESSION_TYPES),
                has_any_block,
                ~has_incomplete_block,
            )
        )
        return result.scalar_one()
