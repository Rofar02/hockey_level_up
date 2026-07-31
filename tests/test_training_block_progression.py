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
from app.models.schedule import DaySessionType
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
