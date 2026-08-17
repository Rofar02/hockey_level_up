"""ScheduleService._pick_main's diversity axis: movement_pattern, not
target_stat (see its docstring for the full rationale).

Off-ice exercises only ever have 4 possible primary target_stat values
(strength/agility/intellect/endurance), which made 4 a hard ceiling on an
off-ice MAIN block no matter what MAIN_EXERCISE_COUNT_RANGE configured --
this is the structural bug from backlog item #3 (party sessions "always ~2,
not 6"; solo sessions "always ~3 main exercises"). movement_pattern has 10
values, so the same MAIN_EXERCISE_COUNT_RANGE range (5-6 in accumulation) is
now actually reachable.

Also verifies a multi-pattern-tagged exercise is never picked twice just
because it satisfies more than one pattern bucket (see the picked_ids
exclusion in _pick_main).
"""
import random
import uuid

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import (
    EquipmentType,
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    MovementPattern,
    TrainingPhase,
)
from app.models.user import User
from app.services.schedule_service import ScheduleService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"axis_{unique}",
        email=f"axis_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        level=15,
    )


def _make_exercise(name: str) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        equipment_type=EquipmentType.BODYWEIGHT,
    )


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, equipment_access, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


@pytest.mark.asyncio
async def test_off_ice_main_block_is_no_longer_capped_at_four(db_session) -> None:
    """5 distinct movement_pattern-tagged candidates (one per pattern) with
    accumulation's count range (5-6, see MAIN_EXERCISE_COUNT_RANGE) must
    all be reachable -- the old target_stat axis had only 4 off-ice values
    and could never get past 4 no matter the configured range."""
    user = _make_user()
    db_session.add(user)

    patterns = [
        MovementPattern.HIP_HINGE,
        MovementPattern.SQUAT,
        MovementPattern.PUSH,
        MovementPattern.PULL,
        MovementPattern.ROTATION,
    ]
    exercises = [_make_exercise(f"main-{pattern.value}") for pattern in patterns]
    db_session.add_all(exercises)
    db_session.add_all([
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=pattern)
        for exercise, pattern in zip(exercises, patterns)
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert len(picked) == 5


@pytest.mark.asyncio
async def test_multi_pattern_exercise_is_not_picked_twice(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    """An exercise tagged with two patterns (e.g. a Bulgarian split squat
    tagged both squat and hip_hinge) can satisfy either bucket, but must
    only ever fill one MAIN slot, not two."""
    monkeypatch.setattr(random, "randint", lambda a, b: b)

    user = _make_user()
    db_session.add(user)

    dual = _make_exercise("dual-pattern")
    other = _make_exercise("other-pattern")
    db_session.add_all([dual, other])
    db_session.add_all([
        ExerciseMovementPattern(exercise_id=dual.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=dual.id, movement_pattern=MovementPattern.HIP_HINGE),
        ExerciseMovementPattern(exercise_id=other.id, movement_pattern=MovementPattern.PUSH),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [dual, other])
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert sorted(e.name for e in picked) == ["dual-pattern", "other-pattern"]
