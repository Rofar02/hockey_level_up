import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan

TRAINING_SESSION_TYPES = (DaySessionType.ON_ICE, DaySessionType.OFF_ICE)


async def has_missed_training_day(
    session: AsyncSession, user_id: uuid.UUID, from_date: date, to_date: date
) -> bool:
    """True if a planned on/off-ice day strictly between from_date and
    to_date has no completed SessionBlock.

    A date with no DayPlan at all, or a DayPlan with session_type=REST,
    never counts as missed -- only a day the plan actually scheduled
    training for, and that training never happened, breaks a streak.
    Shared by streak_consumer (writes) and ProgressService.get_streak
    (lazy read-time check) so both agree on what counts as a break.
    """
    if to_date - from_date <= timedelta(days=1):
        return False  # nothing strictly between two consecutive (or equal) dates

    completed_block_exists = (
        select(SessionBlock.id)
        .join(TrainingSession, SessionBlock.session_id == TrainingSession.id)
        .where(
            TrainingSession.day_plan_id == DayPlan.id,
            SessionBlock.completed_at.is_not(None),
        )
        .exists()
    )

    result = await session.execute(
        select(DayPlan.id)
        .join(WeeklyPlan, DayPlan.weekly_plan_id == WeeklyPlan.id)
        .where(
            WeeklyPlan.user_id == user_id,
            DayPlan.date > from_date,
            DayPlan.date < to_date,
            DayPlan.session_type.in_(TRAINING_SESSION_TYPES),
            ~completed_block_exists,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None
