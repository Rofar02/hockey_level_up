"""Release plan step 5.2 (2026-10-09): the week reacting to real leg load
after an ice day or a game -- SHADOW MODE. It works out what it would do
and logs it ("week_load_shadow"), changing nothing; the log is reviewed
before settings.week_load_reaction_enabled and an actual change are added.
See app.core.week_load for the thresholds.

Acute = the leg dose of the last 48 hours (gym blocks done + ice charges),
undecayed. Habitual = the average 48-hour dose over the last 28 days, so
the threshold is the player's own: four ice sessions a week is normal for
a student, not an overload.
"""
import logging
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.muscle_load import GAIN_PER_DIFFICULTY_LEVEL, ICE_SESSION_DOSE
from app.core.week_load import (
    ACUTE_WINDOW_HOURS,
    HABITUAL_WINDOW_DAYS,
    HEAVY_PLANNED_LOAD,
    LEG_MUSCLES,
    LOOKAHEAD_HOURS,
    is_overloaded,
)
from app.models.exercise import Exercise, ExerciseMuscleGroup, MuscleGroup
from app.models.progress import IceLoadCharge
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.user import User

logger = logging.getLogger(__name__)


async def _dose_events(
    session: AsyncSession, user_id: uuid.UUID, since: datetime
) -> list[tuple[datetime, MuscleGroup, float]]:
    """Every leg dose since `since`: completed gym blocks and ice charges."""
    events: list[tuple[datetime, MuscleGroup, float]] = []
    gym = (
        await session.execute(
            select(SessionBlock.completed_at, Exercise.difficulty_level, ExerciseMuscleGroup.muscle_group, ExerciseMuscleGroup.weight)
            .join(Exercise, Exercise.id == SessionBlock.exercise_id)
            .join(ExerciseMuscleGroup, ExerciseMuscleGroup.exercise_id == Exercise.id)
            .join(TrainingSession, TrainingSession.id == SessionBlock.session_id)
            .join(DayPlan, DayPlan.id == TrainingSession.day_plan_id)
            .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
            .where(
                WeeklyPlan.user_id == user_id,
                SessionBlock.completed_at >= since,
                ExerciseMuscleGroup.muscle_group.in_(LEG_MUSCLES),
            )
        )
    ).all()
    for completed_at, difficulty, muscle, weight in gym:
        events.append((completed_at, muscle, difficulty * GAIN_PER_DIFFICULTY_LEVEL * weight))
    # Dated by when the ice was over, not when the report (or the 24-hour
    # default) came in; a charge from before ice_ended_at existed: its update.
    ice_at = func.coalesce(IceLoadCharge.ice_ended_at, IceLoadCharge.updated_at)
    ice = (
        await session.execute(
            select(ice_at, IceLoadCharge.scale).where(IceLoadCharge.user_id == user_id, ice_at >= since)
        )
    ).all()
    for at, scale in ice:
        for muscle in LEG_MUSCLES:
            events.append((at, muscle, ICE_SESSION_DOSE[muscle] * scale))
    return events


async def _next_heavy_leg_day(
    session: AsyncSession, user_id: uuid.UUID, now: datetime, today: date
) -> tuple[DayPlan, dict] | None:
    """A gym day from the player's own today within LOOKAHEAD_HOURS, not
    started, whose planned leg load reaches HEAVY_PLANNED_LOAD on some leg
    muscle."""
    days = (
        await session.scalars(
            select(DayPlan)
            .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
            .where(
                WeeklyPlan.user_id == user_id,
                DayPlan.session_type == DaySessionType.OFF_ICE,
                DayPlan.date >= today,
                DayPlan.date <= today + timedelta(hours=LOOKAHEAD_HOURS),
            )
            .order_by(DayPlan.date)
        )
    ).all()
    for day in days:
        rows = (
            await session.execute(
                select(SessionBlock.completed_at, Exercise.difficulty_level, ExerciseMuscleGroup.muscle_group, ExerciseMuscleGroup.weight)
                .join(TrainingSession, TrainingSession.id == SessionBlock.session_id)
                .join(Exercise, Exercise.id == SessionBlock.exercise_id)
                .join(ExerciseMuscleGroup, ExerciseMuscleGroup.exercise_id == Exercise.id)
                .where(TrainingSession.day_plan_id == day.id, ExerciseMuscleGroup.muscle_group.in_(LEG_MUSCLES))
            )
        ).all()
        if any(completed_at is not None for completed_at, *_ in rows):
            continue
        planned: dict[str, float] = defaultdict(float)
        for _, difficulty, muscle, weight in rows:
            planned[str(muscle)] += difficulty * GAIN_PER_DIFFICULTY_LEVEL * weight
        if any(value >= HEAVY_PLANNED_LOAD for value in planned.values()):
            return day, dict(planned)
    return None


async def evaluate_week_after_ice(session: AsyncSession, user_id: uuid.UUID, now: datetime | None = None) -> dict | None:
    """What 5.2 would do right now -- None when nothing. Never writes."""
    now = now or datetime.now(timezone.utc)
    events = await _dose_events(session, user_id, now - timedelta(days=HABITUAL_WINDOW_DAYS))
    acute_since = now - timedelta(hours=ACUTE_WINDOW_HOURS)
    windows = HABITUAL_WINDOW_DAYS * 24 / ACUTE_WINDOW_HOURS
    overloaded: dict[str, dict[str, float]] = {}
    for muscle in LEG_MUSCLES:
        acute = sum(dose for at, m, dose in events if m == muscle and at >= acute_since)
        habitual = sum(dose for _, m, dose in events if m == muscle) / windows
        if is_overloaded(acute, habitual):
            overloaded[str(muscle)] = {"acute": round(acute, 1), "habitual": round(habitual, 1)}
    if not overloaded:
        return None
    user = await session.get(User, user_id)
    try:
        today = now.astimezone(ZoneInfo((user.timezone if user else None) or "UTC")).date()
    except Exception:
        today = now.date()
    heavy = await _next_heavy_leg_day(session, user_id, now, today)
    if heavy is None:
        return None
    day, planned = heavy
    return {"overloaded": overloaded, "day": day.date.isoformat(), "planned": planned, "action": "swap_or_lighten"}


async def shadow_check(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Log-only hook after an ice charge; never lets an error reach the
    report the player is saving: it runs in a savepoint, so a failed
    query can't poison the report's own transaction."""
    try:
        async with session.begin_nested():
            decision = await evaluate_week_after_ice(session, user_id)
    except Exception:
        logger.exception("week_load_shadow failed for user_id=%s", user_id)
        return
    if decision is not None:
        logger.info("week_load_shadow user_id=%s would=%s", user_id, decision)
