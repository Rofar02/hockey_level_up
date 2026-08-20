"""ExerciseService.list_equipment_requirements (GET
/exercises/equipment-requirements) -- Stage 2.3 (2026-08-20 planning
session): bulk, non-admin-gated read backing the onboarding/profile
inventory screen's live "unlocked N exercises" counter. Doesn't isolate
against the real seeded catalog (unlike the _pick_main test files) --
looks up this test's own exercise by id in the full result instead, since
the point here is the shape/correctness of one row, not an exact count.
"""
import uuid

import pytest

from app.models.exercise import (
    EquipmentItem,
    Exercise,
    ExerciseCategory,
    ExerciseEquipmentItem,
    TrainingPhase,
)
from app.services.exercise_service import ExerciseService


def _make_exercise(category: ExerciseCategory = ExerciseCategory.OFF_ICE) -> Exercise:
    unique = uuid.uuid4().hex[:8]
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {unique}",
        category=category,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )


@pytest.mark.asyncio
async def test_includes_required_items_for_an_off_ice_exercise(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    db_session.add_all([
        ExerciseEquipmentItem(exercise_id=exercise.id, equipment_item=EquipmentItem.KETTLEBELL),
        ExerciseEquipmentItem(exercise_id=exercise.id, equipment_item=EquipmentItem.STEP_PLATFORM),
    ])
    await db_session.flush()

    requirements = await ExerciseService(db_session).list_equipment_requirements()

    row = next(r for r in requirements if r.exercise_id == exercise.id)
    assert set(row.equipment_items) == {EquipmentItem.KETTLEBELL, EquipmentItem.STEP_PLATFORM}


@pytest.mark.asyncio
async def test_bodyweight_exercise_has_an_empty_list_not_a_missing_row(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    requirements = await ExerciseService(db_session).list_equipment_requirements()

    row = next(r for r in requirements if r.exercise_id == exercise.id)
    assert row.equipment_items == []


@pytest.mark.asyncio
async def test_on_ice_exercises_are_excluded(db_session) -> None:
    exercise = _make_exercise(category=ExerciseCategory.ON_ICE)
    db_session.add(exercise)
    await db_session.flush()

    requirements = await ExerciseService(db_session).list_equipment_requirements()

    assert all(r.exercise_id != exercise.id for r in requirements)
