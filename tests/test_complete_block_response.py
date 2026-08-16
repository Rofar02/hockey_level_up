"""SessionBlockService.complete_block must return a SessionBlockRead, not the
raw ORM SessionBlock -- the router (app/routers/session_blocks.py) declares
response_model=SessionBlockRead, whose exercise.target_stats field isn't a
plain ORM attribute (see exercise_to_read's docstring in
app/schemas/exercise.py). Returning the ORM object 500ed on every call
(FastAPI's response validation couldn't populate target_stats), even though
the block was already committed complete -- this test exercises the service
directly (no HTTP layer) but asserts the exact shape FastAPI's response
validation requires, so it fails the same way the router did before the fix.
"""
import uuid
from datetime import date

import pytest

from app.models.exercise import (
    EquipmentType,
    Exercise,
    ExerciseCategory,
    ExerciseTargetStat,
    TargetStat,
    TrainingPhase,
)
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.user import User
from app.schemas.schedule import SessionBlockRead
from app.services.session_block_service import SessionBlockService

TODAY = date(2026, 3, 10)


@pytest.mark.asyncio
async def test_complete_block_returns_a_valid_session_block_read(db_session) -> None:
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"complete_{unique}",
        email=f"complete_{unique}@example.com",
        password_hash="irrelevant",
    )
    db_session.add(user)

    exercise = Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {unique}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=3,
        equipment_type=EquipmentType.GYM,
    )
    db_session.add(exercise)
    await db_session.flush()
    db_session.add(
        ExerciseTargetStat(
            id=uuid.uuid4(), exercise_id=exercise.id, target_stat=TargetStat.STRENGTH, order=0
        )
    )

    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY)
    db_session.add(weekly_plan)
    await db_session.flush()
    day_plan = DayPlan(
        id=uuid.uuid4(),
        weekly_plan_id=weekly_plan.id,
        date=TODAY,
        session_type=DaySessionType.OFF_ICE,
    )
    db_session.add(day_plan)
    block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0)
    training_session = TrainingSession(id=uuid.uuid4(), day_plan_id=day_plan.id, blocks=[block])
    db_session.add(training_session)
    await db_session.flush()

    result = await SessionBlockService(db_session).complete_block(block.id, user)

    assert isinstance(result, SessionBlockRead)
    assert result.completed_at is not None
    assert result.exercise.target_stats == [TargetStat.STRENGTH]
