"""GET /schedule/day-plan?date=... -- a single day by exact date, independent
of which week is "current"/"next" right now.

Backs HomePage's activity-calendar day-detail modal: that calendar (GET
/users/me/activity-calendar) only reports a per-day completed boolean, not
a block-by-block breakdown, and only days inside the currently-loaded
WeeklyPlan could show their exercise list before this endpoint existed --
any day from a past week (or the previous session's week) came back
"детали пока недоступны" even though the data was there all along.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app.models.exercise import Exercise, ExerciseCategory, TrainingPhase
from app.models.schedule import (
    DayPlan,
    DaySessionType,
    SessionBlock,
    TrainingBlock,
    TrainingSession,
    WeeklyPlan,
)
from app.models.user import User
from app.services.schedule_service import ScheduleService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"dayplan_{unique}",
        email=f"dayplan_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise() -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.ON_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )


def _monday_of(reference: date) -> date:
    return reference - timedelta(days=reference.weekday())


@pytest.mark.asyncio
async def test_get_day_plan_for_date_returns_blocks_for_a_week_outside_current(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    # A week well before "today" -- get_current_weekly_plan/get_weekly_plan
    # (both scoped to a whole WeeklyPlan by week_start_date) would never
    # surface this on their own; the calendar can still show it as a past
    # activity day via GET /users/me/activity-calendar.
    last_monday = _monday_of(date.today()) - timedelta(days=21)

    block = TrainingBlock(
        id=uuid.uuid4(), user_id=user.id, block_number=1, phase_started_at=last_monday
    )
    db_session.add(block)
    await db_session.flush()

    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=last_monday, training_block_id=block.id
    )
    session_block = SessionBlock(
        id=uuid.uuid4(),
        phase=TrainingPhase.MAIN,
        exercise_id=exercise.id,
        order=0,
        completed_at=date.today(),
    )
    weekly_plan.day_plans.append(
        DayPlan(
            id=uuid.uuid4(),
            date=last_monday,
            session_type=DaySessionType.ON_ICE,
            training_session=TrainingSession(id=uuid.uuid4(), blocks=[session_block]),
        )
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    service = ScheduleService(db_session)
    result = await service.get_day_plan_for_date(user, last_monday)

    assert result.date == last_monday
    assert result.session_type == DaySessionType.ON_ICE
    assert result.training_session is not None
    assert len(result.training_session.blocks) == 1
    assert result.training_session.blocks[0].exercise.id == exercise.id
    assert result.training_session.blocks[0].exercise.name == exercise.name


@pytest.mark.asyncio
async def test_get_day_plan_for_date_404s_when_no_day_plan_exists(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = ScheduleService(db_session)
    target = date.today() - timedelta(days=100)
    with pytest.raises(HTTPException) as exc_info:
        await service.get_day_plan_for_date(user, target)

    assert exc_info.value.status_code == 404
    assert target.isoformat() in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_day_plan_for_date_rest_day_has_no_training_session(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    monday = _monday_of(date.today()) - timedelta(days=7)
    block = TrainingBlock(id=uuid.uuid4(), user_id=user.id, block_number=1, phase_started_at=monday)
    db_session.add(block)
    await db_session.flush()

    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=monday, training_block_id=block.id
    )
    rest_day = monday + timedelta(days=1)
    weekly_plan.day_plans.append(
        DayPlan(id=uuid.uuid4(), date=rest_day, session_type=DaySessionType.REST)
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    service = ScheduleService(db_session)
    result = await service.get_day_plan_for_date(user, rest_day)

    assert result.session_type == DaySessionType.REST
    assert result.training_session is None
