import uuid
from datetime import date, timedelta

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.progress import TrainingStreak
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.training_diary import TrainingDiaryEntry

TRAINING_SESSION_TYPES = (DaySessionType.ON_ICE, DaySessionType.OFF_ICE)
ICE_TYPES = (DaySessionType.ON_ICE, DaySessionType.GAME)


def _ice_trained(plan=DayPlan):
    """An ice day / game the player went to (2026-10-12): its report is
    sent and isn't «не был». The preparation checklist is optional, so the
    report alone closes the day for the streak and the calendar too."""
    return (
        select(TrainingDiaryEntry.id)
        .join(TrainingSession, TrainingSession.id == TrainingDiaryEntry.training_session_id)
        .where(
            TrainingSession.day_plan_id == plan.id,
            TrainingDiaryEntry.reported_at.is_not(None),
            TrainingDiaryEntry.skipped.is_(False),
        )
        .exists()
    )


def _plan_done(plan):
    """One DayPlan trained: every block done or skipped (at least one), or
    -- an ice day / game -- its report sent and not «не был»."""
    has_any_block = exists().where(SessionBlock.session_id == TrainingSession.id)
    has_incomplete_block = exists().where(
        SessionBlock.session_id == TrainingSession.id,
        SessionBlock.completed_at.is_(None),
        SessionBlock.skipped_at.is_(None),
    )
    session_fully_completed = (
        select(TrainingSession.id)
        .where(TrainingSession.day_plan_id == plan.id, has_any_block, ~has_incomplete_block)
        .exists()
    )
    return or_(session_fully_completed, _ice_trained(plan))


async def credit_streak_day(session: AsyncSession, user_id: uuid.UUID, day: date) -> None:
    """The streak's credit for a day trained -- streak_consumer's rule, for
    an ice report (2026-10-12). Dated by the ice day itself, so a report
    sent the next morning counts for yesterday; one older than the last
    credited day changes nothing (has_missed_training_day sees it anyway).
    Doesn't commit."""
    streak = (
        await session.execute(select(TrainingStreak).where(TrainingStreak.user_id == user_id).with_for_update())
    ).scalar_one_or_none()
    if streak is None:
        streak = TrainingStreak(user_id=user_id, current_streak=0, longest_streak=0, last_activity_date=None)
        session.add(streak)
    last = streak.last_activity_date
    if last is not None and day <= last:
        return
    if last is not None and not await has_missed_training_day(session, user_id, last, day):
        streak.current_streak += 1
    else:
        streak.current_streak = 1
    streak.longest_streak = max(streak.longest_streak, streak.current_streak)
    streak.last_activity_date = day


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
            # A skip resolves a block for calendar purposes exactly like a
            # real completion does (media-player redesign, 2026-08-28) --
            # see is_session_fully_completed's identical reasoning.
            func.count(SessionBlock.id).filter(
                or_(SessionBlock.completed_at.is_not(None), SessionBlock.skipped_at.is_not(None))
            ),
            _ice_trained().label("ice_trained"),
            DayPlan.is_extra,
        )
        .join(WeeklyPlan, DayPlan.weekly_plan_id == WeeklyPlan.id)
        .outerjoin(TrainingSession, TrainingSession.day_plan_id == DayPlan.id)
        .outerjoin(SessionBlock, SessionBlock.session_id == TrainingSession.id)
        .where(
            WeeklyPlan.user_id == user_id,
            DayPlan.date >= from_date,
            DayPlan.date <= to_date,
        )
        .group_by(DayPlan.id, DayPlan.date, DayPlan.session_type, DayPlan.is_extra)
        .order_by(DayPlan.date)
    )
    # One row per date, typed by its main day. A double day (step 6) is
    # done when either of its trainings is (review 12.10, 6): a gym trained
    # before "иду" moved it to the extra day stays done.
    by_date: dict[date, DayActivity] = {}
    done_dates: set[date] = set()
    for day, session_type, total_blocks, completed_blocks, ice_trained, is_extra in result.all():
        if (total_blocks > 0 and total_blocks == completed_blocks) or (session_type in ICE_TYPES and ice_trained):
            done_dates.add(day)
        if not is_extra:
            by_date[day] = DayActivity(day, session_type, False)
    for day, activity in by_date.items():
        activity.fully_completed = day in done_dates
    return [by_date[day] for day in sorted(by_date)]


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
                SessionBlock.skipped_at.is_(None),
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

    # Review 12.10, 6: a date is trained when any of its plans is -- the
    # main day or a double day's extra gym (a gym done before "иду" moved
    # it to the extra day).
    other = aliased(DayPlan)
    other_week = aliased(WeeklyPlan)
    date_trained = (
        select(other.id)
        .join(other_week, other.weekly_plan_id == other_week.id)
        .where(other_week.user_id == user_id, other.date == DayPlan.date, _plan_done(other))
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
            # A double day's extra gym (step 6) never breaks the streak --
            # the date counts through its main ice/game day.
            DayPlan.is_extra.is_(False),
            ~date_trained,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None
