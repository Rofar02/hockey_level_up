"""SessionBlockService's training_completed publication: fires exactly once,
at the moment the *last* remaining block in a TrainingSession is completed
-- never on partial completion, never twice. Same fixture shape as
test_has_missed_training_day.py (WeeklyPlan/DayPlan/SessionBlock built
directly against the rollback-at-teardown db_session fixture).
"""
import uuid
from datetime import date

import pytest

from app.models.exercise import Exercise, ExerciseCategory, TrainingPhase
from app.models.outbox import OutboxEvent
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.user import User
from app.services.session_block_service import TRAINING_COMPLETED_EVENT, SessionBlockService
from sqlalchemy import select

TODAY = date(2026, 3, 10)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"training_{unique}",
        email=f"training_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise() -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=3,
    )


async def _setup_training(
    db_session, user_id: uuid.UUID, session_type: DaySessionType, num_blocks: int
) -> tuple[DayPlan, TrainingSession, list[SessionBlock]]:
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user_id, week_start_date=TODAY)
    db_session.add(weekly_plan)
    await db_session.flush()
    day_plan = DayPlan(
        id=uuid.uuid4(), weekly_plan_id=weekly_plan.id, date=TODAY, session_type=session_type
    )
    db_session.add(day_plan)
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()
    blocks = [
        SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=i)
        for i in range(num_blocks)
    ]
    training_session = TrainingSession(id=uuid.uuid4(), day_plan_id=day_plan.id, blocks=blocks)
    db_session.add(training_session)
    await db_session.flush()
    return day_plan, training_session, blocks


async def _training_completed_events(db_session, training_session_id: uuid.UUID) -> list[OutboxEvent]:
    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == TRAINING_COMPLETED_EVENT)
    )
    return [
        event
        for event in result.scalars().all()
        if event.payload.get("training_session_id") == str(training_session_id)
    ]


@pytest.mark.asyncio
async def test_no_event_while_blocks_remain_incomplete(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    _day_plan, training_session, blocks = await _setup_training(
        db_session, user.id, DaySessionType.OFF_ICE, num_blocks=2
    )

    service = SessionBlockService(db_session)
    await service.complete_block(blocks[0].id, user)

    assert await _training_completed_events(db_session, training_session.id) == []


@pytest.mark.asyncio
async def test_event_fires_exactly_once_when_last_block_completes(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    day_plan, training_session, blocks = await _setup_training(
        db_session, user.id, DaySessionType.ON_ICE, num_blocks=3
    )

    service = SessionBlockService(db_session)
    await service.complete_block(blocks[0].id, user)
    await service.complete_block(blocks[1].id, user)
    assert await _training_completed_events(db_session, training_session.id) == []

    await service.complete_block(blocks[2].id, user)

    events = await _training_completed_events(db_session, training_session.id)
    assert len(events) == 1
    assert events[0].payload == {
        "user_id": str(user.id),
        "training_session_id": str(training_session.id),
        "day_plan_id": str(day_plan.id),
        "session_type": DaySessionType.ON_ICE.value,
    }


@pytest.mark.asyncio
async def test_single_block_session_fires_on_its_only_completion(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    _day_plan, training_session, blocks = await _setup_training(
        db_session, user.id, DaySessionType.OFF_ICE, num_blocks=1
    )

    await SessionBlockService(db_session).complete_block(blocks[0].id, user)

    assert len(await _training_completed_events(db_session, training_session.id)) == 1


@pytest.mark.asyncio
async def test_completing_an_already_completed_session_never_reachable_twice(db_session) -> None:
    """Once every block is done, there's no remaining incomplete block left
    to complete -- so there is no code path that could re-fire the event for
    the same session. Documented here as a regression guard: re-completing
    the *last* block again 409s (already-completed) before the training-
    completed check ever runs a second time.
    """
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    _day_plan, training_session, blocks = await _setup_training(
        db_session, user.id, DaySessionType.OFF_ICE, num_blocks=1
    )

    service = SessionBlockService(db_session)
    await service.complete_block(blocks[0].id, user)
    assert len(await _training_completed_events(db_session, training_session.id)) == 1

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.complete_block(blocks[0].id, user)
    assert exc_info.value.status_code == 409
    # Still exactly one -- the repeat call never reached the outbox write.
    assert len(await _training_completed_events(db_session, training_session.id)) == 1
