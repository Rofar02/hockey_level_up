"""ScheduleService._enforce_muscle_group_cap: the final whole-session
coherence pass Stage 2.4's own plan text asked for ("не более N упражнений
на одну мышцу... точечная замена кандидата в конфликтующей роли, не
пересборка всей сессии"), run once after all four _pick_main roles are
filled. See test_pick_main_muscle_balance.py for the per-pick soft
preference this sits on top of -- that check only ever sees the pool at
the moment its own slot is filled, so it can't retroactively notice that a
*later* pick will also load the same muscle group. This file proves the
gap that leaves open, and that the final pass closes it.

Same isolation/determinism conventions as test_pick_main_muscle_balance.py:
random.randint/choice/shuffle monkeypatched, all-role-4-only patterns
(ROTATION/ANKLE_MOBILITY/HIP_MOBILITY/SHOULDER_MOBILITY) so roles 1-3
contribute nothing and every pick is deterministic and isolated.
"""
import random
import uuid

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseMuscleGroup,
    ExerciseTargetStat,
    MovementPattern,
    MuscleGroup,
    TargetStat,
    TrainingPhase,
)
from app.models.user import User
from app.services.schedule_service import ScheduleService


@pytest.fixture(autouse=True)
def deterministic_random(monkeypatch: pytest.MonkeyPatch) -> None:
    # 4 MAIN slots -- enough room for all four role-4-only patterns below
    # to each contribute one pick.
    monkeypatch.setattr(random, "randint", lambda a, b: 4)
    monkeypatch.setattr(random, "choice", lambda pool: sorted(pool, key=lambda e: e.name)[0])
    monkeypatch.setattr(random, "shuffle", lambda seq: None)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"coherence_{unique}",
        email=f"coherence_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise(
    name: str, pattern: MovementPattern, muscle_group: MuscleGroup
) -> tuple[Exercise, ExerciseTargetStat, ExerciseMovementPattern, ExerciseMuscleGroup]:
    exercise = Exercise(
        id=uuid.uuid4(), name=name, category=ExerciseCategory.OFF_ICE, phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )
    return (
        exercise,
        ExerciseTargetStat(exercise_id=exercise.id, target_stat=TargetStat.STRENGTH, order=0),
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=pattern),
        ExerciseMuscleGroup(exercise_id=exercise.id, muscle_group=muscle_group, weight=1.0),
    )


def _add_all(db_session, rows) -> list[Exercise]:
    db_session.add_all([e for e, _, _, _ in rows])
    db_session.add_all([s for _, s, _, _ in rows])
    db_session.add_all([p for _, _, p, _ in rows])
    db_session.add_all([m for _, _, _, m in rows])
    return [e for e, _, _, _ in rows]


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


@pytest.mark.asyncio
async def test_retroactively_fixes_a_pileup_the_per_pick_check_could_not_see(db_session) -> None:
    """ROTATION is picked first, while nothing is loaded yet -- so the
    per-pick soft check has no reason to prefer "B-rotation-calves" over
    "A-rotation-core" (alphabetical tie-break wins with an empty
    loaded-groups set). Only once ANKLE_MOBILITY/HIP_MOBILITY/
    SHOULDER_MOBILITY have *also* landed on CORE does the pile-up (4
    exercises, one over MAX_EXERCISES_PER_MUSCLE_GROUP=3) become visible --
    the final pass retroactively swaps the ROTATION pick for the CALVES
    alternative that was sitting unused in its own pattern's pool all
    along."""
    user = _make_user()
    db_session.add(user)
    exercises = _add_all(db_session, [
        _make_exercise("A-rotation-core", MovementPattern.ROTATION, MuscleGroup.CORE),
        _make_exercise("B-rotation-calves", MovementPattern.ROTATION, MuscleGroup.CALVES),
        _make_exercise("C-ankle-core", MovementPattern.ANKLE_MOBILITY, MuscleGroup.CORE),
        _make_exercise("D-hip-core", MovementPattern.HIP_MOBILITY, MuscleGroup.CORE),
        _make_exercise("E-shoulder-core", MovementPattern.SHOULDER_MOBILITY, MuscleGroup.CORE),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == [
        "B-rotation-calves", "C-ankle-core", "D-hip-core", "E-shoulder-core",
    ]


@pytest.mark.asyncio
async def test_at_the_cap_is_not_a_violation(db_session) -> None:
    """Exactly MAX_EXERCISES_PER_MUSCLE_GROUP (3) exercises sharing a
    muscle group is the normal, expected case -- "не более N", N itself is
    allowed -- so the session must come back completely untouched."""
    user = _make_user()
    db_session.add(user)
    exercises = _add_all(db_session, [
        _make_exercise("A-rotation-core", MovementPattern.ROTATION, MuscleGroup.CORE),
        _make_exercise("B-ankle-core", MovementPattern.ANKLE_MOBILITY, MuscleGroup.CORE),
        _make_exercise("C-hip-core", MovementPattern.HIP_MOBILITY, MuscleGroup.CORE),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["A-rotation-core", "B-ankle-core", "C-hip-core"]


@pytest.mark.asyncio
async def test_leaves_the_pileup_when_genuinely_no_substitute_exists(db_session) -> None:
    """Every one of the 4 patterns has exactly one candidate, all sharing
    CORE -- a real catalog-scarcity case with nothing to point-fix. Must
    still return all 4 (never drop a slot), same "honest residual gap over
    a silently emptied slot" convention as _apply_muscle_balance's own
    no-alternative case."""
    user = _make_user()
    db_session.add(user)
    exercises = _add_all(db_session, [
        _make_exercise("A-rotation-core", MovementPattern.ROTATION, MuscleGroup.CORE),
        _make_exercise("B-ankle-core", MovementPattern.ANKLE_MOBILITY, MuscleGroup.CORE),
        _make_exercise("C-hip-core", MovementPattern.HIP_MOBILITY, MuscleGroup.CORE),
        _make_exercise("D-shoulder-core", MovementPattern.SHOULDER_MOBILITY, MuscleGroup.CORE),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == [
        "A-rotation-core", "B-ankle-core", "C-hip-core", "D-shoulder-core",
    ]
