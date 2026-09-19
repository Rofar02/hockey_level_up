"""2026-09-19 audit round 3 item #4: squat/hip_hinge/push/pull were left
out of ROTATING_PATTERNS' same-variant session cap (see round 1 audit
item #1 / tests/test_pick_main_rotating_patterns.py) because
ARCHETYPE_ELIGIBLE_PATTERNS already splits them by load type
(strength/power/skill) -- but that split is across *different* stimulus
lines, not variety *within* one. A squat/POWER pin still held the exact
same variant for the whole training block regardless of how many
unrelated (real content, no catalog gap: 39 squat/power candidates on
the real catalog) alternatives existed. This file covers the extension
(_SESSION_CAP_ROTATED_PATTERNS in schedule_service.py) -- same mechanism
as test_pick_main_rotating_patterns.py, now reaching squat/hip_hinge/
push/pull too, with the archetype line kept independent (a squat/POWER
pin rotates without ever touching squat/STRENGTH's own pin/counter).
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
    StimulusType,
    TrainingPhase,
    UserMovementPatternVariant,
)
from app.models.schedule import BlockPhase, TrainingBlock
from app.models.user import User
from app.services.schedule_service import ScheduleService

TODAY = date(2026, 9, 19)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"archrot_{unique}",
        email=f"archrot_{unique}@example.com",
        password_hash="irrelevant",
        level=15,
    )


def _make_block(user: User) -> TrainingBlock:
    return TrainingBlock(user_id=user.id, block_number=1, phase=BlockPhase.ACCUMULATION)


def _make_squat_exercise(name: str, *, stimulus_type: StimulusType) -> tuple[Exercise, ExerciseMovementPattern]:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        stimulus_type=stimulus_type,
    )
    return exercise, ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT)


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


async def _get_pin(db_session, user: User, archetype: StimulusType) -> UserMovementPatternVariant:
    result = await db_session.execute(
        select(UserMovementPatternVariant).where(
            UserMovementPatternVariant.user_id == user.id,
            UserMovementPatternVariant.category == ExerciseCategory.OFF_ICE,
            UserMovementPatternVariant.movement_pattern == MovementPattern.SQUAT,
            UserMovementPatternVariant.archetype == archetype,
        )
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_squat_power_pin_is_forced_to_rotate_once_the_session_limit_is_reached(
    db_session, monkeypatch
) -> None:
    import random

    monkeypatch.setattr(random, "randint", lambda a, b: 1)

    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    power_a, pattern_a = _make_squat_exercise("Squat-Power-A", stimulus_type=StimulusType.POWER)
    power_b, pattern_b = _make_squat_exercise("Squat-Power-B", stimulus_type=StimulusType.POWER)
    db_session.add_all([power_a, power_b, pattern_a, pattern_b])
    block = _make_block(user)
    db_session.add(block)
    await db_session.flush()

    # squat/POWER pin at the session cap -- last_chosen_at left unset so
    # choose_archetype (no real history for POWER) still resolves POWER
    # for this pattern (an untried archetype outranks a dated one).
    db_session.add(
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.SQUAT,
            archetype=StimulusType.POWER, exercise_id=power_a.id, block_number=1, times_chosen=3,
        )
    )
    # An unrelated squat/STRENGTH pin, already dated so it never wins
    # archetype selection this call -- must stay completely untouched.
    strength_ex, strength_pattern = _make_squat_exercise("Squat-Strength", stimulus_type=StimulusType.STRENGTH)
    db_session.add_all([strength_ex, strength_pattern])
    db_session.add(
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.SQUAT,
            archetype=StimulusType.STRENGTH, exercise_id=strength_ex.id, block_number=1,
            times_chosen=2, last_chosen_at=TODAY,
        )
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [power_a, power_b, strength_ex])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
    )

    assert [e.name for e in picked] == ["Squat-Power-B"]

    power_pin = await _get_pin(db_session, user, StimulusType.POWER)
    assert power_pin.exercise_id == power_b.id
    assert power_pin.times_chosen == 1

    strength_pin = await _get_pin(db_session, user, StimulusType.STRENGTH)
    assert strength_pin.exercise_id == strength_ex.id
    assert strength_pin.times_chosen == 2


@pytest.mark.asyncio
async def test_squat_power_pin_holds_below_the_session_limit(db_session, monkeypatch) -> None:
    import random

    monkeypatch.setattr(random, "randint", lambda a, b: 1)

    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    power_a, pattern_a = _make_squat_exercise("Squat-Power-A", stimulus_type=StimulusType.POWER)
    power_b, pattern_b = _make_squat_exercise("Squat-Power-B", stimulus_type=StimulusType.POWER)
    db_session.add_all([power_a, power_b, pattern_a, pattern_b])
    block = _make_block(user)
    db_session.add(block)
    await db_session.flush()
    db_session.add(
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.SQUAT,
            archetype=StimulusType.POWER, exercise_id=power_a.id, block_number=1, times_chosen=1,
        )
    )
    # A dated squat/STRENGTH pin, same as the rotation-forced test above --
    # makes choose_archetype deterministically resolve POWER for squat
    # this call (an entirely untried archetype always outranks a dated
    # one), rather than leaving POWER vs. the also-untried SKILL slot to
    # an unmocked random.choice tie-break.
    strength_ex, strength_pattern = _make_squat_exercise("Squat-Strength", stimulus_type=StimulusType.STRENGTH)
    db_session.add_all([strength_ex, strength_pattern])
    db_session.add(
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.SQUAT,
            archetype=StimulusType.STRENGTH, exercise_id=strength_ex.id, block_number=1,
            times_chosen=2, last_chosen_at=TODAY,
        )
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [power_a, power_b, strength_ex])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
    )

    assert [e.name for e in picked] == ["Squat-Power-A"]
    pin = await _get_pin(db_session, user, StimulusType.POWER)
    assert pin.times_chosen == 2
