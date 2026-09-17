"""2026-09-17 (audit item #3): TrainingSessionRead.has_diary_entry -- backs
TodayCard's "Заполнить дневник" step. None for off_ice/rest (the diary step
doesn't apply there at all, see TrainingSessionPage.tsx's own on_ice/game
gate on TrainingDiaryCard); bool for on_ice/game, true as soon as any
TrainingDiaryEntry row exists for the session -- including a "quietly
skipped" one whose note is None, since a row existing at all is what marks
the step done, not whether it says anything.
"""
import uuid
from datetime import date, timedelta

import pytest

from app.models.exercise import Exercise, ExerciseCategory, TrainingPhase
from app.models.schedule import (
    DayPlan,
    DaySessionType,
    SessionBlock,
    TrainingBlock,
    TrainingSession,
    WeeklyPlan,
)
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.services.schedule_service import ScheduleService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"diaryflag_{unique}",
        email=f"diaryflag_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise(*, category: ExerciseCategory = ExerciseCategory.ON_ICE) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=category,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )


def _monday_of(reference: date) -> date:
    return reference - timedelta(days=reference.weekday())


async def _seed_week(db_session, user: User, session_type: DaySessionType) -> tuple[WeeklyPlan, TrainingSession]:
    monday = _monday_of(date.today()) - timedelta(days=14)
    block = TrainingBlock(id=uuid.uuid4(), user_id=user.id, block_number=1, phase_started_at=monday)
    db_session.add(block)
    await db_session.flush()

    exercise = _make_exercise(
        category=ExerciseCategory.ON_ICE if session_type != DaySessionType.OFF_ICE else ExerciseCategory.OFF_ICE
    )
    db_session.add(exercise)
    await db_session.flush()

    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=monday, training_block_id=block.id
    )
    session_block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0)
    training_session = TrainingSession(id=uuid.uuid4(), blocks=[session_block])
    weekly_plan.day_plans.append(
        DayPlan(id=uuid.uuid4(), date=monday, session_type=session_type, training_session=training_session)
    )
    db_session.add(weekly_plan)
    await db_session.flush()
    return weekly_plan, training_session


@pytest.mark.asyncio
async def test_on_ice_without_a_diary_entry_is_false(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    _, training_session = await _seed_week(db_session, user, DaySessionType.ON_ICE)

    service = ScheduleService(db_session)
    result = await service.get_day_plan_for_date(user, training_session.day_plan.date)

    assert result.training_session is not None
    assert result.training_session.has_diary_entry is False


@pytest.mark.asyncio
async def test_on_ice_with_a_quietly_skipped_entry_is_true(db_session) -> None:
    """A diary entry saved with note=None (the "Пропустить" flow) still
    counts as done -- the row's mere existence is the signal."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    _, training_session = await _seed_week(db_session, user, DaySessionType.ON_ICE)
    db_session.add(
        TrainingDiaryEntry(user_id=user.id, training_session_id=training_session.id, note=None)
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    result = await service.get_day_plan_for_date(user, training_session.day_plan.date)

    assert result.training_session.has_diary_entry is True


@pytest.mark.asyncio
async def test_game_day_diary_flag_behaves_like_on_ice(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    _, training_session = await _seed_week(db_session, user, DaySessionType.GAME)
    db_session.add(
        TrainingDiaryEntry(user_id=user.id, training_session_id=training_session.id, note="Good game")
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    result = await service.get_day_plan_for_date(user, training_session.day_plan.date)

    assert result.training_session.has_diary_entry is True


@pytest.mark.asyncio
async def test_off_ice_has_diary_entry_is_none(db_session) -> None:
    """off_ice never gets a TrainingDiaryCard at all -- has_diary_entry
    must be None (not False), so the frontend can tell "not applicable"
    apart from "not done yet"."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    _, training_session = await _seed_week(db_session, user, DaySessionType.OFF_ICE)

    service = ScheduleService(db_session)
    result = await service.get_day_plan_for_date(user, training_session.day_plan.date)

    assert result.training_session.has_diary_entry is None


@pytest.mark.asyncio
async def test_weekly_plan_batches_the_diary_flag_across_days(db_session) -> None:
    """Same computation through the WeeklyPlanRead path (get_weekly_plan),
    not just the single-day one -- both funnel through _to_read_schema."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    weekly_plan, training_session = await _seed_week(db_session, user, DaySessionType.ON_ICE)
    db_session.add(
        TrainingDiaryEntry(user_id=user.id, training_session_id=training_session.id, note="ok")
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    result = await service.get_weekly_plan(user, weekly_plan.week_start_date)

    day = next(d for d in result.day_plans if d.training_session is not None)
    assert day.training_session.has_diary_entry is True
