"""PATCH /schedule/weekly/current: per-date partial success.

A week with Monday already started (completed SessionBlock) and Tuesday
untouched -- patching both in one request must change only Tuesday and
report a conflict for Monday, without rolling back Tuesday's change.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TargetStat, TrainingPhase
from app.models.schedule import (
    DayPlan,
    DaySessionType,
    SessionBlock,
    TrainingBlock,
    TrainingSession,
    WeeklyPlan,
)
from app.models.user import User
from app.schemas.schedule import DayPlanIn, WeeklyPlanPatch
from app.services.schedule_service import ScheduleService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"user_{unique}",
        email=f"user_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
    )


def _make_exercise(category: ExerciseCategory) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=category,
        phase=TrainingPhase.MAIN,
        target_stat=TargetStat.STRENGTH,
        difficulty_level=1,
        equipment_type=EquipmentType.BODYWEIGHT,
    )


@pytest.mark.asyncio
async def test_patch_partial_success_skips_started_day_but_applies_the_rest(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    block = TrainingBlock(id=uuid.uuid4(), user_id=user.id, block_number=1, week_in_block=1)
    db_session.add(block)
    await db_session.flush()

    monday = date.today() - timedelta(days=date.today().weekday())
    tuesday = monday + timedelta(days=1)

    monday_exercise = _make_exercise(ExerciseCategory.ON_ICE)
    tuesday_exercise = _make_exercise(ExerciseCategory.ON_ICE)
    db_session.add_all([monday_exercise, tuesday_exercise])
    await db_session.flush()

    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=monday, training_block_id=block.id
    )

    monday_block = SessionBlock(
        id=uuid.uuid4(),
        phase=TrainingPhase.MAIN,
        exercise_id=monday_exercise.id,
        order=0,
        completed_at=datetime.now(timezone.utc),
    )
    monday_plan = DayPlan(
        id=uuid.uuid4(),
        date=monday,
        session_type=DaySessionType.ON_ICE,
        training_session=TrainingSession(id=uuid.uuid4(), blocks=[monday_block]),
    )

    tuesday_block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=tuesday_exercise.id, order=0
    )
    tuesday_plan = DayPlan(
        id=uuid.uuid4(),
        date=tuesday,
        session_type=DaySessionType.ON_ICE,
        training_session=TrainingSession(id=uuid.uuid4(), blocks=[tuesday_block]),
    )

    weekly_plan.day_plans.append(monday_plan)
    weekly_plan.day_plans.append(tuesday_plan)
    for offset in range(2, 7):
        weekly_plan.day_plans.append(
            DayPlan(
                id=uuid.uuid4(),
                date=monday + timedelta(days=offset),
                session_type=DaySessionType.REST,
            )
        )

    db_session.add(weekly_plan)
    await db_session.flush()

    monday_block_id = monday_block.id
    tuesday_block_id = tuesday_block.id

    service = ScheduleService(db_session)
    result = await service.patch_current_weekly_plan(
        user,
        WeeklyPlanPatch(
            days=[
                DayPlanIn(date=monday, session_type=DaySessionType.OFF_ICE),
                DayPlanIn(date=tuesday, session_type=DaySessionType.OFF_ICE),
            ]
        ),
    )

    # Exactly one conflict, for Monday, with a human-readable reason.
    assert len(result.conflicts) == 1
    assert result.conflicts[0].date == monday
    assert result.conflicts[0].detail == "Этот день уже начат, нельзя изменить"

    day_by_date = {day.date: day for day in result.weekly_plan.day_plans}

    # Monday untouched: still on_ice, same completed block still there.
    monday_result = day_by_date[monday]
    assert monday_result.session_type == DaySessionType.ON_ICE
    assert monday_result.training_session is not None
    assert [b.id for b in monday_result.training_session.blocks] == [monday_block_id]
    assert monday_result.training_session.blocks[0].completed_at is not None

    # Tuesday changed: now off_ice, old (uncompleted) block replaced.
    tuesday_result = day_by_date[tuesday]
    assert tuesday_result.session_type == DaySessionType.OFF_ICE
    assert tuesday_result.training_session is not None
    assert tuesday_block_id not in [b.id for b in tuesday_result.training_session.blocks]

    # The old Tuesday block is actually gone from the DB, not just
    # unreferenced -- proves the replace path deletes rather than orphans.
    assert await db_session.get(SessionBlock, tuesday_block_id) is None
    # The old Monday block is still there, byte for byte.
    assert await db_session.get(SessionBlock, monday_block_id) is not None


@pytest.mark.asyncio
async def test_patch_no_current_weekly_plan_raises_404(db_session) -> None:
    from fastapi import HTTPException

    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = ScheduleService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.patch_current_weekly_plan(
            user,
            WeeklyPlanPatch(days=[DayPlanIn(date=date.today(), session_type=DaySessionType.REST)]),
        )
    assert exc_info.value.status_code == 404
