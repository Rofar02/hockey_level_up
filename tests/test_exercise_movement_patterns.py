"""ExerciseMovementPattern replace/list round-trip (PUT/GET
/exercises/{id}/movement-patterns) -- a bare full-replace tag set, no
per-pair metadata (unlike SkillTag's required transfer_note), see
app.repositories.exercise_repository.replace_movement_patterns.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.exercise import (
    EquipmentType,
    Exercise,
    ExerciseCategory,
    MovementPattern,
    TrainingPhase,
)
from app.services.exercise_service import ExerciseService


def _make_exercise() -> Exercise:
    unique = uuid.uuid4().hex[:8]
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {unique}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        equipment_type=EquipmentType.BODYWEIGHT,
    )


@pytest.mark.asyncio
async def test_replace_is_full_replacement_and_dedupes(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    service = ExerciseService(db_session)

    first = await service.replace_movement_patterns(
        exercise.id, [MovementPattern.SQUAT, MovementPattern.SQUAT, MovementPattern.PUSH]
    )
    assert set(first) == {MovementPattern.SQUAT, MovementPattern.PUSH}

    second = await service.replace_movement_patterns(exercise.id, [MovementPattern.PULL])
    assert set(second) == {MovementPattern.PULL}

    listed = await service.list_movement_patterns(exercise.id)
    assert set(listed) == {MovementPattern.PULL}


@pytest.mark.asyncio
async def test_replace_with_empty_list_clears_all_patterns(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    service = ExerciseService(db_session)
    await service.replace_movement_patterns(exercise.id, [MovementPattern.HIP_HINGE])
    cleared = await service.replace_movement_patterns(exercise.id, [])
    assert cleared == []
    assert await service.list_movement_patterns(exercise.id) == []


@pytest.mark.asyncio
async def test_list_on_untagged_exercise_returns_empty(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    service = ExerciseService(db_session)
    assert await service.list_movement_patterns(exercise.id) == []


@pytest.mark.asyncio
async def test_replace_rejects_unknown_exercise_id(db_session) -> None:
    service = ExerciseService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.replace_movement_patterns(uuid.uuid4(), [MovementPattern.CORE])
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_rejects_unknown_exercise_id(db_session) -> None:
    service = ExerciseService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.list_movement_patterns(uuid.uuid4())
    assert exc_info.value.status_code == 404
