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
