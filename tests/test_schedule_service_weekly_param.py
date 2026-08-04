"""GET/PATCH /schedule/weekly with an optional week_start_date query param.

Verifies:
  1. Explicit week_start_date does a direct (user, week) lookup -- finds a
     plan for exactly that week, 404s with a message distinct from "no
     current plan" when that specific week was never declared (even if a
     plan exists for some other week, e.g. the current one).
  2. week_start_date omitted aliases byte-for-byte to the existing /current
     behavior -- get_current_weekly_plan/patch_current_weekly_plan are
     untouched (they now delegate internally, but their own tests already
     cover them; this file only checks the new aliasing path matches).
  3. Patching an explicit week works for a week that is NOT "current" by
     date.today() -- get_current's range check would never find it, which
     is exactly the gap this feature closes.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

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
from app.schemas.schedule import DayPlanIn, WeeklyPlanCreate, WeeklyPlanPatch
from app.services.schedule_service import ScheduleService
from app.services.training_block_service import TrainingBlockService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"weekparam_{unique}",
        email=f"weekparam_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
    )


def _make_exercise() -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.ON_ICE,
        phase=TrainingPhase.MAIN,
        target_stat=TargetStat.STRENGTH,
        difficulty_level=1,
        equipment_type=EquipmentType.BODYWEIGHT,
    )


def _monday_of(reference: date) -> date:
    return reference - timedelta(days=reference.weekday())


async def _make_weekly_plan(
    db_session, user: User, week_start_date: date, block_number: int = 1
) -> WeeklyPlan:
    """A full 7-day WeeklyPlan (Monday on_ice, rest of the week REST), each
    under its own ad-hoc TrainingBlock -- block_number must be distinct per
    call for the same user (uq_training_blocks_user_block_number)."""
    block = TrainingBlock(
        id=uuid.uuid4(),
        user_id=user.id,
        block_number=block_number,
        week_in_block=1,
        anchor_week_start_date=week_start_date,
    )
    db_session.add(block)
    await db_session.flush()

    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=week_start_date, training_block_id=block.id
    )
    weekly_plan.day_plans.append(
        DayPlan(
            id=uuid.uuid4(),
            date=week_start_date,
            session_type=DaySessionType.ON_ICE,
            training_session=TrainingSession(
                id=uuid.uuid4(),
                blocks=[
                    SessionBlock(
                        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0
                    )
                ],
            ),
        )
    )
    for offset in range(1, 7):
        weekly_plan.day_plans.append(
            DayPlan(
                id=uuid.uuid4(),
                date=week_start_date + timedelta(days=offset),
                session_type=DaySessionType.REST,
            )
        )

    db_session.add(weekly_plan)
    await db_session.flush()
    return weekly_plan


# --- GET /schedule/weekly ---


@pytest.mark.asyncio
async def test_get_weekly_plan_with_explicit_week_start_date_returns_that_week(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    this_monday = _monday_of(date.today())
    next_monday = this_monday + timedelta(days=7)

    await _make_weekly_plan(db_session, user, this_monday, block_number=1)
    next_week = await _make_weekly_plan(db_session, user, next_monday, block_number=2)

    service = ScheduleService(db_session)
    result = await service.get_weekly_plan(user, next_monday)

    assert result.id == next_week.id
    assert result.week_start_date == next_monday


@pytest.mark.asyncio
async def test_get_weekly_plan_with_explicit_week_start_date_404s_when_absent(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    this_monday = _monday_of(date.today())
    # Only the current week exists -- next week was never declared.
    await _make_weekly_plan(db_session, user, this_monday, block_number=1)

    service = ScheduleService(db_session)
    next_monday = this_monday + timedelta(days=7)
    with pytest.raises(HTTPException) as exc_info:
        await service.get_weekly_plan(user, next_monday)

    assert exc_info.value.status_code == 404
    # Distinct from "No current weekly plan" -- a plan exists (for the
    # current week), just not for the week actually asked about.
    assert exc_info.value.detail != "No current weekly plan"
    assert "No weekly plan for week starting" in exc_info.value.detail
    assert next_monday.isoformat() in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_weekly_plan_without_param_matches_get_current(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    this_monday = _monday_of(date.today())
    await _make_weekly_plan(db_session, user, this_monday, block_number=1)

    service = ScheduleService(db_session)
    via_current = await service.get_current_weekly_plan(user)
    via_param = await service.get_weekly_plan(user, None)

    assert via_param.id == via_current.id
    assert via_param.week_start_date == via_current.week_start_date


@pytest.mark.asyncio
async def test_get_weekly_plan_without_param_404s_like_get_current(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = ScheduleService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.get_weekly_plan(user, None)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No current weekly plan"


# --- PATCH /schedule/weekly ---


@pytest.mark.asyncio
async def test_patch_weekly_plan_with_explicit_week_start_date_patches_that_week(db_session) -> None:
    """The whole point of this feature: patching a week that is NOT
    date.today()'s current week -- get_current's range check would never
    find it at all."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    this_monday = _monday_of(date.today())
    next_monday = this_monday + timedelta(days=7)

    await _make_weekly_plan(db_session, user, this_monday, block_number=1)
    await _make_weekly_plan(db_session, user, next_monday, block_number=2)

    service = ScheduleService(db_session)
    result = await service.patch_weekly_plan(
        user,
        WeeklyPlanPatch(days=[DayPlanIn(date=next_monday, session_type=DaySessionType.OFF_ICE)]),
        next_monday,
    )

    assert result.conflicts == []
    assert result.weekly_plan.week_start_date == next_monday
    day_by_date = {day.date: day for day in result.weekly_plan.day_plans}
    assert day_by_date[next_monday].session_type == DaySessionType.OFF_ICE

    # The *current* week's plan is untouched by a patch scoped to next week.
    current_plan = await service.get_current_weekly_plan(user)
    assert current_plan.week_start_date == this_monday
    current_day_by_date = {day.date: day for day in current_plan.day_plans}
    assert current_day_by_date[this_monday].session_type == DaySessionType.ON_ICE


@pytest.mark.asyncio
async def test_patch_weekly_plan_with_explicit_week_start_date_404s_when_absent(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    this_monday = _monday_of(date.today())
    next_monday = this_monday + timedelta(days=7)
    await _make_weekly_plan(db_session, user, this_monday, block_number=1)

    service = ScheduleService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.patch_weekly_plan(
            user,
            WeeklyPlanPatch(days=[DayPlanIn(date=next_monday, session_type=DaySessionType.OFF_ICE)]),
            next_monday,
        )

    assert exc_info.value.status_code == 404
    assert "No weekly plan for week starting" in exc_info.value.detail


@pytest.mark.asyncio
async def test_patch_weekly_plan_without_param_matches_patch_current(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    this_monday = _monday_of(date.today())
    await _make_weekly_plan(db_session, user, this_monday, block_number=1)
    target_date = this_monday + timedelta(days=2)

    service = ScheduleService(db_session)
    result = await service.patch_weekly_plan(
        user,
        WeeklyPlanPatch(days=[DayPlanIn(date=target_date, session_type=DaySessionType.OFF_ICE)]),
        None,
    )

    day_by_date = {day.date: day for day in result.weekly_plan.day_plans}
    assert day_by_date[target_date].session_type == DaySessionType.OFF_ICE


@pytest.mark.asyncio
async def test_patch_weekly_plan_without_param_404s_like_patch_current(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = ScheduleService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.patch_weekly_plan(
            user,
            WeeklyPlanPatch(days=[DayPlanIn(date=date.today(), session_type=DaySessionType.REST)]),
            None,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No current weekly plan"


# --- End-to-end: create_weekly_plan for the current week, then again for
# next week, exercising both the periodization fix (previous change) and
# these new endpoints together, the way a real client actually would. ---


def _full_week_payload(week_start_date: date) -> WeeklyPlanCreate:
    return WeeklyPlanCreate(
        days=[
            DayPlanIn(
                date=week_start_date + timedelta(days=i),
                session_type=DaySessionType.OFF_ICE if i % 2 == 0 else DaySessionType.REST,
            )
            for i in range(7)
        ]
    )


@pytest.mark.asyncio
async def test_create_current_then_next_week_advances_periodization_by_one_and_both_are_gettable(
    db_session,
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    schedule = ScheduleService(db_session)
    blocks = TrainingBlockService(db_session)

    this_monday = _monday_of(date.today())
    next_monday = this_monday + timedelta(days=7)

    await schedule.create_weekly_plan(user, _full_week_payload(this_monday))
    after_first = await blocks.get_current(user.id)
    assert (after_first.block_number, after_first.week_in_block) == (1, 1)

    # Real next real week, declared right after -- must advance by exactly
    # 1 step (the periodization-fix regression this used to get wrong: 2
    # create_weekly_plan calls in a row used to advance by 2 regardless of
    # how many real weeks separated them).
    await schedule.create_weekly_plan(user, _full_week_payload(next_monday))
    after_second = await blocks.get_current(user.id)
    assert (after_second.block_number, after_second.week_in_block) == (1, 2)

    # Both weeks are independently fetchable through the new endpoint, and
    # the current week is unaffected by next week having been declared.
    current = await schedule.get_weekly_plan(user, None)
    assert current.week_start_date == this_monday

    upcoming = await schedule.get_weekly_plan(user, next_monday)
    assert upcoming.week_start_date == next_monday
    assert upcoming.id != current.id
