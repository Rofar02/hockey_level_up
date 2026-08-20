"""ExerciseMuscleGroup replace/list round-trip (PUT/GET
/exercises/{id}/muscle-groups) -- Stage 2.1 (2026-08-20 planning session).
Weighted list, not a bare tag set like ExerciseMovementPattern (see
test_exercise_movement_patterns.py) -- weights are validated not to exceed
1.0 in total, same precedent as skill_service._validate_weight_sum.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    MuscleGroup,
    TrainingPhase,
)
from app.schemas.exercise import MuscleGroupWeight
from app.services.exercise_service import ExerciseService


def _make_exercise() -> Exercise:
    unique = uuid.uuid4().hex[:8]
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {unique}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )


@pytest.mark.asyncio
async def test_replace_is_full_replacement_and_dedupes(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    service = ExerciseService(db_session)

    first = await service.replace_muscle_groups(
        exercise.id,
        [
            MuscleGroupWeight(muscle_group=MuscleGroup.QUADS, weight=0.3),
            # Repeated group -- last value wins, same dict.fromkeys-style
            # dedupe as replace_movement_patterns.
            MuscleGroupWeight(muscle_group=MuscleGroup.QUADS, weight=0.6),
            MuscleGroupWeight(muscle_group=MuscleGroup.GLUTES, weight=0.4),
        ],
    )
    assert {(g.muscle_group, g.weight) for g in first} == {
        (MuscleGroup.QUADS, 0.6),
        (MuscleGroup.GLUTES, 0.4),
    }

    second = await service.replace_muscle_groups(
        exercise.id, [MuscleGroupWeight(muscle_group=MuscleGroup.CHEST, weight=1.0)]
    )
    assert {(g.muscle_group, g.weight) for g in second} == {(MuscleGroup.CHEST, 1.0)}

    listed = await service.list_muscle_groups(exercise.id)
    assert {(g.muscle_group, g.weight) for g in listed} == {(MuscleGroup.CHEST, 1.0)}


@pytest.mark.asyncio
async def test_replace_with_empty_list_clears_all_groups(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    service = ExerciseService(db_session)
    await service.replace_muscle_groups(
        exercise.id, [MuscleGroupWeight(muscle_group=MuscleGroup.BACK, weight=1.0)]
    )
    cleared = await service.replace_muscle_groups(exercise.id, [])
    assert cleared == []
    assert await service.list_muscle_groups(exercise.id) == []


@pytest.mark.asyncio
async def test_list_on_untagged_exercise_returns_empty(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    service = ExerciseService(db_session)
    assert await service.list_muscle_groups(exercise.id) == []


@pytest.mark.asyncio
async def test_replace_rejects_weights_summing_over_one(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    service = ExerciseService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.replace_muscle_groups(
            exercise.id,
            [
                MuscleGroupWeight(muscle_group=MuscleGroup.QUADS, weight=0.7),
                MuscleGroupWeight(muscle_group=MuscleGroup.GLUTES, weight=0.4),
            ],
        )
    assert exc_info.value.status_code == 409
    # The rejected attempt must not have partially written anything.
    assert await service.list_muscle_groups(exercise.id) == []


@pytest.mark.asyncio
async def test_replace_rejects_unknown_exercise_id(db_session) -> None:
    service = ExerciseService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.replace_muscle_groups(
            uuid.uuid4(), [MuscleGroupWeight(muscle_group=MuscleGroup.CORE, weight=1.0)]
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_rejects_unknown_exercise_id(db_session) -> None:
    service = ExerciseService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.list_muscle_groups(uuid.uuid4())
    assert exc_info.value.status_code == 404
