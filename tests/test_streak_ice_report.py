"""The ice report closes an ice day for the streak and the calendar
(2026-10-12): the preparation checklist is optional, so a day the player
skated and reported -- without ticking the warm-up -- is a trained day, not
a gap; «не был» still is one. The credit is dated by the ice day."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models.exercise import Exercise, ExerciseCategory, TrainingPhase
from app.models.progress import TrainingStreak
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.training_diary import IceEffort
from app.models.user import User
from app.schemas.training_diary import DiaryReportIn
from app.services.streak_service import has_missed_training_day, list_activity_calendar
from app.services.training_diary_service import TrainingDiaryService
from tests.dates import utc_today


async def _setup(db_session):
    unique = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), username=f"si_{unique}", email=f"si_{unique}@example.com", password_hash="x", timezone="UTC")
    db_session.add(user)
    exercise = Exercise(
        id=uuid.uuid4(), name=f"si prep {unique}", category=ExerciseCategory.ON_ICE, phase=TrainingPhase.WARMUP, difficulty_level=1,
    )
    db_session.add(exercise)
    await db_session.flush()
    today = utc_today()
    ice_day = today - timedelta(days=1)
    ice = TrainingSession(
        id=uuid.uuid4(), blocks=[SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.WARMUP, exercise_id=exercise.id, order=0)]
    )
    day = DayPlan(id=uuid.uuid4(), date=ice_day, session_type=DaySessionType.ON_ICE, training_session=ice)
    db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=ice_day - timedelta(days=ice_day.weekday()), day_plans=[day]))
    # The last credited day before the ice.
    db_session.add(TrainingStreak(user_id=user.id, current_streak=4, longest_streak=4, last_activity_date=ice_day - timedelta(days=1)))
    await db_session.flush()
    return user, ice, ice_day, today


@pytest.mark.asyncio
async def test_a_reported_ice_day_without_prep_ticks_keeps_the_streak(db_session) -> None:
    user, ice, ice_day, today = await _setup(db_session)
    assert await has_missed_training_day(db_session, user.id, ice_day - timedelta(days=1), today) is True

    await TrainingDiaryService(db_session).save_entry(
        user, ice.id, None, DiaryReportIn(duration_minutes=60, effort=IceEffort.NORMAL)
    )

    assert await has_missed_training_day(db_session, user.id, ice_day - timedelta(days=1), today) is False
    streak = await db_session.scalar(select(TrainingStreak).where(TrainingStreak.user_id == user.id))
    # Sent "today", credited for the ice day itself.
    assert streak.current_streak == 5 and streak.last_activity_date == ice_day
    calendar = {d.date: d.fully_completed for d in await list_activity_calendar(db_session, user.id, ice_day, ice_day)}
    assert calendar[ice_day] is True


@pytest.mark.asyncio
async def test_ne_byl_is_still_a_gap(db_session) -> None:
    user, ice, ice_day, today = await _setup(db_session)

    await TrainingDiaryService(db_session).save_entry(user, ice.id, None, DiaryReportIn(skipped=True))

    assert await has_missed_training_day(db_session, user.id, ice_day - timedelta(days=1), today) is True
    streak = await db_session.scalar(select(TrainingStreak).where(TrainingStreak.user_id == user.id))
    assert streak.current_streak == 4 and streak.last_activity_date == ice_day - timedelta(days=1)
    calendar = {d.date: d.fully_completed for d in await list_activity_calendar(db_session, user.id, ice_day, ice_day)}
    assert calendar[ice_day] is False


@pytest.mark.asyncio
async def test_a_done_extra_gym_keeps_the_date_trained(db_session) -> None:
    """Review 12.10, 6: the gym was done, then "иду" made the team's ice the
    main day and moved the gym to the extra one -- the date stays done for
    the calendar and the gap check, whatever the unreported ice."""
    user, _ice, ice_day, today = await _setup(db_session)
    exercise = Exercise(
        id=uuid.uuid4(), name=f"si gym {uuid.uuid4().hex[:6]}", category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN, difficulty_level=3,
    )
    db_session.add(exercise)
    await db_session.flush()
    main_day = await db_session.scalar(select(DayPlan).where(DayPlan.date == ice_day, DayPlan.training_session.has(id=_ice.id)))
    gym = TrainingSession(
        id=uuid.uuid4(),
        blocks=[SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0, completed_at=_now())],
    )
    db_session.add(
        DayPlan(
            id=uuid.uuid4(), weekly_plan_id=main_day.weekly_plan_id, date=ice_day, session_type=DaySessionType.OFF_ICE,
            is_extra=True, time_of_day="morning", training_session=gym,
        )
    )
    await db_session.flush()

    assert await has_missed_training_day(db_session, user.id, ice_day - timedelta(days=1), today) is False
    calendar = await list_activity_calendar(db_session, user.id, ice_day, ice_day)
    assert [(d.date, d.session_type, d.fully_completed) for d in calendar] == [(ice_day, DaySessionType.ON_ICE, True)]


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
