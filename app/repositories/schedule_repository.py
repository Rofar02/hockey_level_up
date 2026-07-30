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

    async def get_session_block_with_owner(self, block_id: uuid.UUID) -> SessionBlock | None:
        query = (
            select(SessionBlock)
            .where(SessionBlock.id == block_id)
            .options(*_SESSION_BLOCK_OWNERSHIP_OPTIONS)
        )
        result = await self._session.execute(query)
        return result.unique().scalar_one_or_none()
