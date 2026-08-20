"""ExerciseTargetStat replace/list round-trip (PUT/GET
/exercises/{id}/target-stats) -- unlike ExerciseMovementPattern, order
matters here: index 0 is the "primary" stat ScheduleService._pick_main/
suggest_party_exercises bucket on for diversity (see
app.repositories.exercise_repository.replace_target_stats).
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    TargetStat,
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
    )


@pytest.mark.asyncio
async def test_replace_is_full_replacement_and_dedupes(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    service = ExerciseService(db_session)

    first = await service.replace_target_stats(
        exercise.id, [TargetStat.STRENGTH, TargetStat.STRENGTH, TargetStat.AGILITY]
    )
    assert first == [TargetStat.STRENGTH, TargetStat.AGILITY]

    second = await service.replace_target_stats(exercise.id, [TargetStat.INTELLECT])
    assert second == [TargetStat.INTELLECT]

    listed = await service.list_target_stats(exercise.id)
    assert listed == [TargetStat.INTELLECT]


@pytest.mark.asyncio
async def test_replace_preserves_submitted_order_as_primary_first(db_session) -> None:
    """List order becomes ExerciseTargetStat.order -- index 0 must round-trip
    as the first element back out, not just be present in the set."""
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    service = ExerciseService(db_session)
    result = await service.replace_target_stats(
        exercise.id, [TargetStat.ENDURANCE, TargetStat.STRENGTH, TargetStat.AGILITY]
    )
    assert result == [TargetStat.ENDURANCE, TargetStat.STRENGTH, TargetStat.AGILITY]

    listed = await service.list_target_stats(exercise.id)
    assert listed == [TargetStat.ENDURANCE, TargetStat.STRENGTH, TargetStat.AGILITY]


@pytest.mark.asyncio
async def test_replace_with_empty_list_clears_all_stats(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    service = ExerciseService(db_session)
    await service.replace_target_stats(exercise.id, [TargetStat.STRENGTH])
    cleared = await service.replace_target_stats(exercise.id, [])
    assert cleared == []
    assert await service.list_target_stats(exercise.id) == []


@pytest.mark.asyncio
async def test_list_on_untagged_exercise_returns_empty(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    service = ExerciseService(db_session)
    assert await service.list_target_stats(exercise.id) == []


@pytest.mark.asyncio
async def test_replace_rejects_unknown_exercise_id(db_session) -> None:
    service = ExerciseService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.replace_target_stats(uuid.uuid4(), [TargetStat.STRENGTH])
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_rejects_unknown_exercise_id(db_session) -> None:
    service = ExerciseService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.list_target_stats(uuid.uuid4())
    assert exc_info.value.status_code == 404
