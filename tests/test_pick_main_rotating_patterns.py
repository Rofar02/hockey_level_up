"""2026-09-17 fix (audit item #1): locomotion/core/coordination/rotation
used to pin one variant for the whole training block (up to
PHASE_CALENDAR_CEILING_WEEKS) -- the direct cause of "same exercise for
weeks" complaints. See app.core.day_archetype.ROTATING_PATTERNS/
ROTATION_SESSION_LIMIT. Isolated to MovementPattern.CORE (role 4 only, no
role-1 explosive-pattern interaction) to keep these deterministic.
"""
import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    MovementPattern,
    TrainingPhase,
    UserMovementPatternVariant,
)
from app.models.schedule import BlockPhase, TrainingBlock
from app.models.user import User
from app.services.schedule_service import ScheduleService

TODAY = date(2026, 9, 17)


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"rotating_{unique}",
        email=f"rotating_{unique}@example.com",
        password_hash="irrelevant",
        level=15,
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_block(user: User, *, block_number: int = 1) -> TrainingBlock:
    return TrainingBlock(user_id=user.id, block_number=block_number, phase=BlockPhase.ACCUMULATION)


def _make_core_exercise(name: str) -> tuple[Exercise, ExerciseMovementPattern]:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )
    return exercise, ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.CORE)


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


async def _get_pin(db_session, user: User) -> UserMovementPatternVariant:
    result = await db_session.execute(
        select(UserMovementPatternVariant).where(
            UserMovementPatternVariant.user_id == user.id,
            UserMovementPatternVariant.category == ExerciseCategory.OFF_ICE,
            UserMovementPatternVariant.movement_pattern == MovementPattern.CORE,
            UserMovementPatternVariant.archetype.is_(None),
        )
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_pin_holds_below_the_session_limit(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    core_a, pattern_a = _make_core_exercise("Core-A")
    core_b, pattern_b = _make_core_exercise("Core-B")
    db_session.add_all([core_a, core_b, pattern_a, pattern_b])
    block = _make_block(user)
    db_session.add(block)
    await db_session.flush()
    db_session.add(
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.CORE,
            archetype=None, exercise_id=core_a.id, block_number=1, times_chosen=1,
        )
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [core_a, core_b])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
    )

    assert [e.name for e in picked] == ["Core-A"]
    pin = await _get_pin(db_session, user)
    assert pin.times_chosen == 2


@pytest.mark.asyncio
async def test_pin_is_forced_to_rotate_once_the_session_limit_is_reached(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    core_a, pattern_a = _make_core_exercise("Core-A")
    core_b, pattern_b = _make_core_exercise("Core-B")
    db_session.add_all([core_a, core_b, pattern_a, pattern_b])
    block = _make_block(user)
    db_session.add(block)
    await db_session.flush()
    db_session.add(
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.CORE,
            archetype=None, exercise_id=core_a.id, block_number=1, times_chosen=3,
        )
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [core_a, core_b])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
    )

    assert [e.name for e in picked] == ["Core-B"]
    pin = await _get_pin(db_session, user)
    assert pin.exercise_id == core_b.id
    assert pin.times_chosen == 1


@pytest.mark.asyncio
async def test_pin_still_force_rotates_through_a_macrocycle_deload_hold(db_session) -> None:
    """2026-09-21 fix: a macrocycle-deload block runs the same full
    mesocycle length as any other block (see is_macrocycle_deload_block's
    own docstring) -- it isn't short, so exempting the session-rotation
    cap here used to let one accessory exercise repeat for the whole
    block (6+ weeks in a real simulation), well past
    ROTATION_SESSION_LIMIT's ~1.5-week intent. Swapping between same-tier
    accessory candidates isn't a load/intensity lever, unlike the
    difficulty-escalation and stimulus-preference-mismatch guards
    elsewhere in this same method, which correctly still hold through a
    deload block -- only this cap's deload exemption was removed.
    """
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    core_a, pattern_a = _make_core_exercise("Core-A")
    core_b, pattern_b = _make_core_exercise("Core-B")
    db_session.add_all([core_a, core_b, pattern_a, pattern_b])
    block = _make_block(user)
    block.is_macrocycle_deload = True
    db_session.add(block)
    await db_session.flush()
    db_session.add(
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.CORE,
            archetype=None, exercise_id=core_a.id, block_number=99, times_chosen=5,
        )
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [core_a, core_b])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
    )

    assert [e.name for e in picked] == ["Core-B"]
    pin = await _get_pin(db_session, user)
    assert pin.exercise_id == core_b.id
    assert pin.times_chosen == 1


@pytest.mark.asyncio
async def test_fresh_first_ever_pin_starts_the_counter_at_one(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    core_a, pattern_a = _make_core_exercise("Core-A")
    db_session.add_all([core_a, pattern_a])
    block = _make_block(user)
    db_session.add(block)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [core_a])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
    )

    assert [e.name for e in picked] == ["Core-A"]
    pin = await _get_pin(db_session, user)
    assert pin.times_chosen == 1
