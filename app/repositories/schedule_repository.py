import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.schedule import DayPlan, SessionBlock, TrainingSession, WeeklyPlan

_SESSION_BLOCK_OWNERSHIP_OPTIONS = (
    selectinload(SessionBlock.exercise),
    selectinload(SessionBlock.session)
    .selectinload(TrainingSession.day_plan)
    .selectinload(DayPlan.weekly_plan),
)

_TRAINING_SESSION_OWNERSHIP_OPTIONS = (
    selectinload(TrainingSession.day_plan).selectinload(DayPlan.weekly_plan),
    selectinload(TrainingSession.blocks),
)

_EAGER_LOAD_OPTIONS = (
    selectinload(WeeklyPlan.day_plans)
    .selectinload(DayPlan.training_session)
    .selectinload(TrainingSession.blocks)
    .selectinload(SessionBlock.exercise),
)


class ScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, weekly_plan: WeeklyPlan) -> WeeklyPlan:
        self._session.add(weekly_plan)
        await self._session.flush()
        return weekly_plan

    async def get_by_id_with_details(self, weekly_plan_id: uuid.UUID) -> WeeklyPlan | None:
        query = (
            select(WeeklyPlan)
            .where(WeeklyPlan.id == weekly_plan_id)
            .options(*_EAGER_LOAD_OPTIONS)
        )
        result = await self._session.execute(query)
        return result.unique().scalar_one_or_none()

    async def get_current(self, user_id: uuid.UUID, today: date) -> WeeklyPlan | None:
        query = (
            select(WeeklyPlan)
            .where(WeeklyPlan.user_id == user_id, WeeklyPlan.week_start_date <= today)
            .options(*_EAGER_LOAD_OPTIONS)
            .order_by(WeeklyPlan.week_start_date.desc())
        )
        result = await self._session.execute(query)
        candidate = result.unique().scalars().first()

        if candidate is None:
            return None
        if today > candidate.week_start_date + timedelta(days=6):
            return None
        return candidate

    async def get_by_week_start_date(
        self, user_id: uuid.UUID, week_start_date: date
    ) -> WeeklyPlan | None:
        """Direct (user_id, week_start_date) lookup -- no "today" range logic,
        unlike get_current. Callers who already know which week they want
        (e.g. "next week") don't need get_current's is-today-still-inside-
        this-week check; they just need the exact row, or None if that week
        was never declared."""
        query = (
            select(WeeklyPlan)
            .where(WeeklyPlan.user_id == user_id, WeeklyPlan.week_start_date == week_start_date)
            .options(*_EAGER_LOAD_OPTIONS)
        )
        result = await self._session.execute(query)
        return result.unique().scalar_one_or_none()

    async def get_day_plan_for_date(self, user_id: uuid.UUID, target_date: date) -> DayPlan | None:
        """Direct (user_id, target_date) lookup via DayPlan.date -- backs
        TrainingPartyService's per-member training-status resolution (same
        date-across-many-users query shape as TeamRatingService's completed-
        trainings aggregate) and ScheduleService.get_day_plan_for_date's
        single-day detail endpoint. Uses ix_day_plans_date rather than
        resolving through a week_start_date first, since the caller only has
        a date, not necessarily "the current week." .exercise is eager-
        loaded alongside .blocks (harmless extra select for the
        TrainingPartyService callers, which don't read it) so the single-day
        detail endpoint can build a full DayPlanRead without a second
        lazy-load round trip.
        """
        query = (
            select(DayPlan)
            .join(WeeklyPlan, DayPlan.weekly_plan_id == WeeklyPlan.id)
            .where(WeeklyPlan.user_id == user_id, DayPlan.date == target_date)
            .options(
                selectinload(DayPlan.training_session)
                .selectinload(TrainingSession.blocks)
                .selectinload(SessionBlock.exercise)
            )
        )
        result = await self._session.execute(query)
        return result.unique().scalar_one_or_none()

    async def get_session_block_with_owner(self, block_id: uuid.UUID) -> SessionBlock | None:
        query = (
            select(SessionBlock)
            .where(SessionBlock.id == block_id)
            .options(*_SESSION_BLOCK_OWNERSHIP_OPTIONS)
        )
        result = await self._session.execute(query)
        return result.unique().scalar_one_or_none()

    async def get_training_session_with_owner(
        self, training_session_id: uuid.UUID
    ) -> TrainingSession | None:
        query = (
            select(TrainingSession)
            .where(TrainingSession.id == training_session_id)
            .options(*_TRAINING_SESSION_OWNERSHIP_OPTIONS)
        )
        result = await self._session.execute(query)
        return result.unique().scalar_one_or_none()
