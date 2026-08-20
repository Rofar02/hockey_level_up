"""ExerciseService.list_catalog_health_issues (GET /exercises/catalog-health,
admin-only) -- Stage 3 (2026-08-20 planning session). Doesn't isolate
against the real seeded catalog (same convention as
test_exercise_equipment_requirements.py) -- looks up this test's own
exercise by id in the full result instead, since the real catalog has
plenty of its own gaps today and the point here is per-exercise
correctness, not an exact count.

Real catalog numbers checked before writing this (2026-08-20): 245/368
off_ice exercises have zero equipment tags, almost all of them legitimately
bodyweight-only -- that's why "equipment_for_tracked_weight" is scoped to
tracks_weight=true exercises only, not a blanket "no equipment" check (see
CatalogHealthIssue's own docstring).
"""
import uuid

import pytest

from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseEquipmentItem,
    ExerciseMovementPattern,
    ExerciseTargetStat,
    EquipmentItem,
    MovementPattern,
    TargetStat,
    TrainingPhase,
    WarmupStage,
)
from app.services.exercise_service import ExerciseService


def _make_exercise(**overrides) -> Exercise:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        name=f"Exercise {unique}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )
    defaults.update(overrides)
    return Exercise(**defaults)


async def _issue_for(db_session, exercise: Exercise) -> dict | None:
    issues = await ExerciseService(db_session).list_catalog_health_issues()
    row = next((r for r in issues if r.exercise_id == exercise.id), None)
    return row


@pytest.mark.asyncio
async def test_fully_tagged_off_ice_exercise_has_no_issues(db_session) -> None:
    exercise = _make_exercise(tracks_weight=False)
    db_session.add(exercise)
    db_session.add(ExerciseTargetStat(exercise_id=exercise.id, target_stat=TargetStat.STRENGTH, order=0))
    db_session.add(ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT))
    await db_session.flush()

    assert await _issue_for(db_session, exercise) is None


@pytest.mark.asyncio
async def test_off_ice_missing_primary_stat_is_flagged(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    db_session.add(ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT))
    await db_session.flush()

    row = await _issue_for(db_session, exercise)
    assert row is not None
    assert "primary_target_stat" in row.missing


@pytest.mark.asyncio
async def test_on_ice_exercise_is_never_flagged_for_missing_primary_stat(db_session) -> None:
    exercise = _make_exercise(category=ExerciseCategory.ON_ICE)
    db_session.add(exercise)
    db_session.add(ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT))
    await db_session.flush()

    row = await _issue_for(db_session, exercise)
    assert row is None


@pytest.mark.asyncio
async def test_missing_movement_pattern_is_flagged_for_either_category(db_session) -> None:
    exercise = _make_exercise(category=ExerciseCategory.ON_ICE)
    db_session.add(exercise)
    await db_session.flush()

    row = await _issue_for(db_session, exercise)
    assert row is not None
    assert "movement_pattern" in row.missing


@pytest.mark.asyncio
async def test_warmup_exercise_without_warmup_stage_is_flagged(db_session) -> None:
    exercise = _make_exercise(phase=TrainingPhase.WARMUP, tracks_weight=False)
    db_session.add(exercise)
    db_session.add(ExerciseTargetStat(exercise_id=exercise.id, target_stat=TargetStat.STRENGTH, order=0))
    db_session.add(ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT))
    await db_session.flush()

    row = await _issue_for(db_session, exercise)
    assert row is not None
    assert row.missing == ["warmup_stage"]


@pytest.mark.asyncio
async def test_warmup_exercise_with_warmup_stage_set_is_not_flagged_for_it(db_session) -> None:
    exercise = _make_exercise(
        phase=TrainingPhase.WARMUP, tracks_weight=False, warmup_stage=WarmupStage.RAISE
    )
    db_session.add(exercise)
    db_session.add(ExerciseTargetStat(exercise_id=exercise.id, target_stat=TargetStat.STRENGTH, order=0))
    db_session.add(ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT))
    await db_session.flush()

    assert await _issue_for(db_session, exercise) is None


@pytest.mark.asyncio
async def test_bodyweight_exercise_with_zero_equipment_is_not_flagged(db_session) -> None:
    """The real-catalog-driven scoping decision: tracks_weight=false + zero
    equipment tags is the normal, healthy state (plain bodyweight work),
    not a gap."""
    exercise = _make_exercise(tracks_weight=False)
    db_session.add(exercise)
    db_session.add(ExerciseTargetStat(exercise_id=exercise.id, target_stat=TargetStat.STRENGTH, order=0))
    db_session.add(ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT))
    await db_session.flush()

    assert await _issue_for(db_session, exercise) is None


@pytest.mark.asyncio
async def test_tracked_weight_exercise_with_zero_equipment_is_flagged(db_session) -> None:
    exercise = _make_exercise(tracks_weight=True)
    db_session.add(exercise)
    db_session.add(ExerciseTargetStat(exercise_id=exercise.id, target_stat=TargetStat.STRENGTH, order=0))
    db_session.add(ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT))
    await db_session.flush()

    row = await _issue_for(db_session, exercise)
    assert row is not None
    assert "equipment_for_tracked_weight" in row.missing


@pytest.mark.asyncio
async def test_tracked_weight_exercise_with_equipment_tagged_is_not_flagged(db_session) -> None:
    exercise = _make_exercise(tracks_weight=True)
    db_session.add(exercise)
    db_session.add(ExerciseTargetStat(exercise_id=exercise.id, target_stat=TargetStat.STRENGTH, order=0))
    db_session.add(ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT))
    db_session.add(ExerciseEquipmentItem(exercise_id=exercise.id, equipment_item=EquipmentItem.DUMBBELLS))
    await db_session.flush()

    assert await _issue_for(db_session, exercise) is None
