"""Phase 9: TrainingBlock progression through POST /schedule/weekly.

Verifies the three behaviors called out for this change:
  1. A user with no TrainingBlock at all gets block_number=1/week_in_block=1
     on their very first weekly declaration.
  2. Five consecutive weekly declarations progress
     1/accum -> 2/accum -> 3/intens -> 4/deload -> (new block) 2/1/accum.
  3. suggested_reassessment flips to True exactly on the week-4 -> new-block
     transition (the 5th declaration), not before.
"""
import uuid
from datetime import date, timedelta

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import EquipmentType
from app.models.schedule import DaySessionType, TrainingBlock
from app.models.user import User
from app.schemas.schedule import DayPlanIn, WeeklyPlanCreate
from app.services.schedule_service import ScheduleService
from app.services.training_block_service import TrainingBlockService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"block_{unique}",
        email=f"block_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
    )


def _week_payload(start: date) -> WeeklyPlanCreate:
    days = [
        DayPlanIn(
            date=start + timedelta(days=i),
            session_type=DaySessionType.OFF_ICE if i % 2 == 0 else DaySessionType.REST,
        )
        for i in range(7)
    ]
    return WeeklyPlanCreate(days=days)


@pytest.mark.asyncio
async def test_five_consecutive_weeks_progress_block_and_flag_reassessment(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    schedule = ScheduleService(db_session)
    blocks = TrainingBlockService(db_session)

    base = date(2026, 1, 5)
    expected = [
        (1, 1, BlockPhase.ACCUMULATION),
        (1, 2, BlockPhase.ACCUMULATION),
        (1, 3, BlockPhase.INTENSIFICATION),
        (1, 4, BlockPhase.DELOAD),
        (2, 1, BlockPhase.ACCUMULATION),
    ]

    for week_index, (exp_block_number, exp_week_in_block, exp_phase) in enumerate(expected):
        assert user.suggested_reassessment is False, f"week {week_index}: flag set too early"

        await schedule.create_weekly_plan(user, _week_payload(base + timedelta(days=7 * week_index)))
        current = await blocks.get_current(user.id)

        assert (current.block_number, current.week_in_block, current.phase) == (
            exp_block_number,
            exp_week_in_block,
            exp_phase,
        ), f"week {week_index}"

        if week_index == 4:
            assert user.suggested_reassessment is True, "flag should flip on the week4->new-block transition"
        else:
            assert user.suggested_reassessment is False


# --- _resolve_training_block: anchor_week_start_date-driven advancement ---
#
# These call _resolve_training_block directly (same convention as
# test_schedule_service_pick_main.py calling service._pick_main directly)
# rather than going through create_weekly_plan, specifically to isolate the
# advancement decision from WeeklyPlan's own (user_id, week_start_date)
# unique constraint -- re-declaring a week that already has a saved
# WeeklyPlan 409s at the DB level regardless of what _resolve_training_block
# decides, which would make "redeclaring the same week doesn't advance"
# untestable through the public API alone.


@pytest.mark.asyncio
async def test_same_week_redeclared_does_not_advance(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = ScheduleService(db_session)
    target = date(2026, 2, 2)

    first = await service._resolve_training_block(user, target)
    assert (first.block_number, first.week_in_block) == (1, 1)

    second = await service._resolve_training_block(user, target)
    assert second.id == first.id
    assert (second.block_number, second.week_in_block) == (1, 1)


@pytest.mark.asyncio
async def test_next_week_advances_by_one(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = ScheduleService(db_session)
    base = date(2026, 2, 2)

    await service._resolve_training_block(user, base)
    result = await service._resolve_training_block(user, base + timedelta(days=7))

    assert (result.block_number, result.week_in_block) == (1, 2)
    assert result.anchor_week_start_date == base + timedelta(days=7)


@pytest.mark.asyncio
async def test_two_real_weeks_ahead_advances_by_two(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = ScheduleService(db_session)
    base = date(2026, 2, 2)

    await service._resolve_training_block(user, base)  # (1, 1)
    result = await service._resolve_training_block(user, base + timedelta(days=14))

    # Jumping 2 real weeks in one call must advance 2 steps (1 -> 3), not 1.
    assert (result.block_number, result.week_in_block) == (1, 3)
    assert result.anchor_week_start_date == base + timedelta(days=14)


@pytest.mark.asyncio
async def test_multi_week_jump_rolls_over_mid_gap_and_flags_reassessment(db_session) -> None:
    """A multi-week jump that crosses the week-4 boundary must roll over to
    a new block_number *during* the gap, not just land wherever `+ weeks_diff`
    would put week_in_block if rollover were ignored."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = ScheduleService(db_session)
    base = date(2026, 2, 2)

    await service._resolve_training_block(user, base)  # (1, 1)
    await service._resolve_training_block(user, base + timedelta(days=7))  # (1, 2)
    landed = await service._resolve_training_block(user, base + timedelta(days=14))  # (1, 3)
    assert (landed.block_number, landed.week_in_block) == (1, 3)
    assert user.suggested_reassessment is False

    # 2 real weeks ahead from week 3: step to 4, then roll over to (2, 1) --
    # not "3 + 2 = 5" and not "stops at 4 without rolling over".
    result = await service._resolve_training_block(user, base + timedelta(days=28))

    assert (result.block_number, result.week_in_block) == (2, 1)
    assert result.anchor_week_start_date == base + timedelta(days=28)
    assert user.suggested_reassessment is True


@pytest.mark.asyncio
async def test_earlier_week_than_anchor_is_a_safe_noop(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = ScheduleService(db_session)
    base = date(2026, 2, 2)

    anchored = await service._resolve_training_block(user, base)
    assert (anchored.block_number, anchored.week_in_block) == (1, 1)

    result = await service._resolve_training_block(user, base - timedelta(days=7))

    # Same row, nothing advanced or rewound -- anchor stays exactly what it
    # was, not moved backward either.
    assert result.id == anchored.id
    assert (result.block_number, result.week_in_block) == (1, 1)
    assert result.anchor_week_start_date == base


@pytest.mark.asyncio
async def test_backfilled_block_with_null_anchor_does_not_crash(db_session) -> None:
    """Simulates a TrainingBlock row from before anchor_week_start_date
    existed, for which the migration's backfill found no WeeklyPlan (so
    anchor stayed NULL) -- must not raise, and must not guess how many
    weeks elapsed."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    block = TrainingBlock(
        user_id=user.id, block_number=1, week_in_block=2, anchor_week_start_date=None
    )
    db_session.add(block)
    await db_session.flush()

    service = ScheduleService(db_session)
    target = date(2026, 3, 2)

    result = await service._resolve_training_block(user, target)

    assert result.id == block.id
    # Treated as the first real planning call under this block: anchors to
    # the target week, but week_in_block is left exactly as it was.
    assert result.week_in_block == 2
    assert result.anchor_week_start_date == target
