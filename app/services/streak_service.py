import uuid
from datetime import date, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan

TRAINING_SESSION_TYPES = (DaySessionType.ON_ICE, DaySessionType.OFF_ICE)


class DayActivity:
    """One calendar day's plan + completion state -- what
    GET /users/me/activity-calendar returns, and the data HomePage.tsx's
    calendar needs to render a real month of history instead of just the
    current week's WeeklyPlan plus a single TrainingStreak.last_activity_date
    marker (see that file's own comment on why it couldn't do this before
    2026-08-19)."""

    __slots__ = ("date", "session_type", "fully_completed")

    def __init__(self, day: date, session_type: DaySessionType, fully_completed: bool) -> None:
        self.date = day
        self.session_type = session_type
        self.fully_completed = fully_completed


async def list_activity_calendar(
    session: AsyncSession, user_id: uuid.UUID, from_date: date, to_date: date
) -> list[DayActivity]:
    """Every DayPlan for user_id in [from_date, to_date] (inclusive), each
    with whether its session was *fully* completed -- same "every
    SessionBlock done, at least one exists" bar is_session_fully_completed/
    has_missed_training_day use for streak purposes, so the calendar and
    the streak number always agree on which days actually count. One
    aggregate query for the whole range (COUNT of blocks vs COUNT of
    completed_at per day), not a per-day existence check, since this is
    always scanning many days at once rather than checking a single one.

    A date with no DayPlan at all (outside any WeeklyPlan, or a future date
    nothing's been generated for yet) is simply absent from the result --
    same "missing means nothing to report" contract as
    ExerciseRepository.list_movement_patterns_by_exercise.
    """
    result = await session.execute(
        select(
            DayPlan.date,
            DayPlan.session_type,
            func.count(SessionBlock.id),
            func.count(SessionBlock.completed_at),
        )
        .join(WeeklyPlan, DayPlan.weekly_plan_id == WeeklyPlan.id)
        .outerjoin(TrainingSession, TrainingSession.day_plan_id == DayPlan.id)
        .outerjoin(SessionBlock, SessionBlock.session_id == TrainingSession.id)
        .where(
            WeeklyPlan.user_id == user_id,
            DayPlan.date >= from_date,
            DayPlan.date <= to_date,
        )
        .group_by(DayPlan.date, DayPlan.session_type)
        .order_by(DayPlan.date)
    )
    return [
        DayActivity(day, session_type, total_blocks > 0 and total_blocks == completed_blocks)
        for day, session_type, total_blocks, completed_blocks in result.all()
    ]


async def is_session_fully_completed(session: AsyncSession, session_block_id: uuid.UUID) -> bool:
    """True once every SessionBlock in the same TrainingSession as
    session_block_id has completed_at set (and the session has at least
    one block at all -- trivially true here since session_block_id is
    itself one).

    Same "a real completed session" bar
    TrainingBlockRepository.count_completed_real_sessions uses for
    periodization progression -- streak credit used to fire on the *first*
    block clicked that day (e.g. one warmup exercise, no MAIN work at all
    completed), which let a day count as "trained" by a much looser bar
    than the one the app's own progression logic uses for the same
    question. Found 2026-08-19: a user with 3/12 blocks done (warmup only,
    zero MAIN) had already been credited a full streak day.
    """
    target_session_id = (
        await session.execute(
            select(SessionBlock.session_id).where(SessionBlock.id == session_block_id)
        )
    ).scalar_one_or_none()
    if target_session_id is None:
        return False

    has_incomplete_block = (
        await session.execute(
            select(SessionBlock.id)
            .where(
                SessionBlock.session_id == target_session_id,
                SessionBlock.completed_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return has_incomplete_block is None


async def has_missed_training_day(
    session: AsyncSession, user_id: uuid.UUID, from_date: date, to_date: date
) -> bool:
    """True if a planned on/off-ice day strictly between from_date and
    to_date doesn't have its session *fully* completed.

    A date with no DayPlan at all, or a DayPlan with session_type REST or
    GAME, never counts as missed -- only a day the plan actually scheduled
    a full training session for, and that training never happened, breaks
    a streak. GAME days are a light activation, not a workout (see
    ScheduleService._build_game_day_session), so they're excluded from
    TRAINING_SESSION_TYPES below the same way REST is, just implicitly
    (only ON_ICE/OFF_ICE are ever "in" it). Shared by streak_consumer
    (writes) and ProgressService.get_streak (lazy read-time check) so both
    agree on what counts as a break.

    "Fully completed" (2026-08-19), not merely "has one completed block"
    -- same bar is_session_fully_completed uses for the day-of check, so a
    day partially clicked through (e.g. only its warmup) isn't silently
    treated as "trained, no gap here" by the *gap* check while the day-of
    check (correctly) withholds credit for that same day.
    """
    if to_date - from_date <= timedelta(days=1):
        return False  # nothing strictly between two consecutive (or equal) dates

    has_any_block = exists().where(SessionBlock.session_id == TrainingSession.id)
    has_incomplete_block = exists().where(
        SessionBlock.session_id == TrainingSession.id, SessionBlock.completed_at.is_(None)
    )
    session_fully_completed = (
        select(TrainingSession.id)
        .where(
            TrainingSession.day_plan_id == DayPlan.id,
            has_any_block,
            ~has_incomplete_block,
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
            ~session_fully_completed,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None
