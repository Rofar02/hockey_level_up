"""Phase 4: TrainingBlock phase progression driven by completed real
sessions (not calendar weeks).

Verifies:
  1. A user with no TrainingBlock gets block_number=1/ACCUMULATION on their
     very first weekly declaration, and repeated weekly declarations with no
     sessions completed do NOT advance the phase on their own (the old
     calendar-driven behavior this replaces).
  2. Completing SESSIONS_TO_ADVANCE_PHASE real (on/off-ice) sessions since
     phase_started_at advances accumulation -> intensification ->
     deload -> (new block) accumulation, one step at a time.
  3. suggested_reassessment/suggested_onice_reassessment flip to True
     exactly on the deload -> new-block transition, not before.
  4. The soft calendar ceiling (PHASE_CALENDAR_CEILING_WEEKS) advances a
     phase even with zero completed sessions, once enough real time has
     passed.
  5. TrainingBlockService.resolve_active_block is idempotent and safe to
     call repeatedly without double-advancing.

Tests that need several real training days to pass between phase
transitions use a `_Clock` and TrainingBlockService's injectable `today`
param rather than the wall clock -- otherwise a session dated in the future
(the only way to dodge WeeklyPlan's per-user-per-week uniqueness constraint
without waiting for real days to pass) would never age out of the *next*
phase's count once phase_started_at catches up to it.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core.training_block import PHASE_CALENDAR_CEILING_WEEKS, SESSIONS_TO_ADVANCE_PHASE
from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TrainingPhase
from app.models.schedule import (
    BlockPhase,
    DayPlan,
    DaySessionType,
    SessionBlock,
    TrainingBlock,
    TrainingSession,
    WeeklyPlan,
)
from app.models.user import User
from app.schemas.schedule import DayPlanIn, WeeklyPlanCreate
from app.services.schedule_service import ScheduleService
from app.services.training_block_service import TrainingBlockService


class _Clock:
    """A controllable "today" -- ticking by whole weeks keeps every session
    in its own WeeklyPlan calendar week (uq_weekly_plans_user_week), and
    ticking by an extra day before each resolve() call keeps a phase's
    phase_started_at strictly after that phase's own last session, so it
    doesn't also get counted toward the next phase.
    """

    def __init__(self, start: date) -> None:
        self.today = start

    def tick_weeks(self, n: int = 1) -> date:
        self.today += timedelta(weeks=n)
        return self.today

    def tick_days(self, n: int = 1) -> date:
        self.today += timedelta(days=n)
        return self.today


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"block_{unique}",
        email=f"block_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
    )


def _rest_week_payload(start: date) -> WeeklyPlanCreate:
    """A week with no on/off-ice days at all -- isolates "declaring a week"
    from "completing a session" so declaring alone can be asserted not to
    advance the phase."""
    days = [DayPlanIn(date=start + timedelta(days=i), session_type=DaySessionType.REST) for i in range(7)]
    return WeeklyPlanCreate(days=days)


async def _complete_real_session(db_session, user: User, block: TrainingBlock, on_date: date) -> None:
    """Creates and completes one off-ice TrainingSession under `block`,
    dated `on_date`. Bypasses ScheduleService's own assembly (which needs a
    seeded catalog) since this file only cares about counting completed
    sessions, not what's inside them.
    """
    exercise = Exercise(
        id=uuid.uuid4(),
        name=f"exercise-{uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        equipment_type=EquipmentType.BODYWEIGHT,
    )
    db_session.add(exercise)
    await db_session.flush()

    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(),
        user_id=user.id,
        week_start_date=on_date - timedelta(days=on_date.weekday()),
        training_block_id=block.id,
    )
    weekly_plan.day_plans.append(
        DayPlan(
            id=uuid.uuid4(),
            date=on_date,
            session_type=DaySessionType.OFF_ICE,
            training_session=TrainingSession(
                id=uuid.uuid4(),
                blocks=[
                    SessionBlock(
                        id=uuid.uuid4(),
                        phase=TrainingPhase.MAIN,
                        exercise_id=exercise.id,
                        order=0,
                        completed_at=datetime.now(timezone.utc),
                    )
                ],
            ),
        )
    )
    db_session.add(weekly_plan)
    await db_session.flush()


async def _complete_a_phase_worth_of_sessions(db_session, user: User, block: TrainingBlock, clock: _Clock) -> None:
    for _ in range(SESSIONS_TO_ADVANCE_PHASE):
        clock.tick_weeks(1)
        await _complete_real_session(db_session, user, block, clock.today)
    clock.tick_days(1)  # strictly after the last session's date


@pytest.mark.asyncio
async def test_declaring_weeks_alone_does_not_advance_the_phase(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    schedule = ScheduleService(db_session)
    blocks = TrainingBlockService(db_session)

    base = date(2026, 1, 5)
    for week_index in range(3):
        await schedule.create_weekly_plan(user, _rest_week_payload(base + timedelta(days=7 * week_index)))

    current = await blocks.get_current(user.id)
    assert (current.block_number, current.phase) == (1, BlockPhase.ACCUMULATION)
    assert current.sessions_completed_in_phase == 0
    assert user.suggested_reassessment is False


@pytest.mark.asyncio
async def test_completed_sessions_advance_through_every_phase_and_roll_over(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    blocks = TrainingBlockService(db_session)
    clock = _Clock(date(2026, 1, 5))
    block = await blocks.get_or_create_and_resolve(user.id, today=clock.today)
    assert (block.block_number, block.phase) == (1, BlockPhase.ACCUMULATION)

    # accumulation -> intensification
    await _complete_a_phase_worth_of_sessions(db_session, user, block, clock)
    block = await blocks.resolve_active_block(user.id, today=clock.today)
    assert (block.block_number, block.phase) == (1, BlockPhase.INTENSIFICATION)
    assert user.suggested_reassessment is False

    # intensification -> deload
    await _complete_a_phase_worth_of_sessions(db_session, user, block, clock)
    block = await blocks.resolve_active_block(user.id, today=clock.today)
    assert (block.block_number, block.phase) == (1, BlockPhase.DELOAD)
    assert user.suggested_reassessment is False

    # deload -> new block (2, ACCUMULATION), reassessment flags flip
    await _complete_a_phase_worth_of_sessions(db_session, user, block, clock)
    block = await blocks.resolve_active_block(user.id, today=clock.today)
    assert (block.block_number, block.phase) == (2, BlockPhase.ACCUMULATION)
    assert user.suggested_reassessment is True
    assert user.suggested_onice_reassessment is True


@pytest.mark.asyncio
async def test_partial_progress_does_not_advance(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    blocks = TrainingBlockService(db_session)
    clock = _Clock(date(2026, 2, 2))
    block = await blocks.get_or_create_and_resolve(user.id, today=clock.today)

    for _ in range(SESSIONS_TO_ADVANCE_PHASE - 1):
        clock.tick_weeks(1)
        await _complete_real_session(db_session, user, block, clock.today)

    resolved = await blocks.resolve_active_block(user.id, today=clock.today)
    assert resolved.phase == BlockPhase.ACCUMULATION
    current = await blocks.get_current(user.id, today=clock.today)
    assert current.sessions_completed_in_phase == SESSIONS_TO_ADVANCE_PHASE - 1


@pytest.mark.asyncio
async def test_calendar_ceiling_advances_phase_with_zero_completed_sessions(db_session) -> None:
    """An inactive user (no completed sessions at all) must still advance
    past a phase once it's run longer than the soft calendar ceiling --
    the safety net this exists for."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    stale_start = date.today() - timedelta(weeks=PHASE_CALENDAR_CEILING_WEEKS + 1)
    block = TrainingBlock(
        user_id=user.id, block_number=1, phase=BlockPhase.ACCUMULATION, phase_started_at=stale_start
    )
    db_session.add(block)
    await db_session.flush()

    blocks = TrainingBlockService(db_session)
    resolved = await blocks.resolve_active_block(user.id)

    assert resolved.phase == BlockPhase.INTENSIFICATION
    assert resolved.phase_started_at == date.today()


@pytest.mark.asyncio
async def test_resolve_active_block_is_idempotent(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    blocks = TrainingBlockService(db_session)
    clock = _Clock(date(2026, 3, 2))
    block = await blocks.get_or_create_and_resolve(user.id, today=clock.today)

    await _complete_a_phase_worth_of_sessions(db_session, user, block, clock)

    first = await blocks.resolve_active_block(user.id, today=clock.today)
    second = await blocks.resolve_active_block(user.id, today=clock.today)

    assert first.id == second.id
    assert (first.phase, second.phase) == (BlockPhase.INTENSIFICATION, BlockPhase.INTENSIFICATION)


@pytest.mark.asyncio
async def test_get_current_404s_when_no_block_exists_yet(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    blocks = TrainingBlockService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await blocks.get_current(user.id)
    assert exc_info.value.status_code == 404
