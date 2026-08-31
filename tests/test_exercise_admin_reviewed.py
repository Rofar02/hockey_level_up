"""Exercise.admin_reviewed -- admin-only checklist flag toggled through
ExerciseService.update_exercise (PATCH /exercises/{id}), same mechanism as
every other partial field on that endpoint. No gameplay logic reads this
field; these tests just confirm the default and the round-trip.
"""
import uuid

import pytest

from app.models.exercise import Exercise, ExerciseCategory, TrainingPhase
from app.schemas.exercise import ExerciseUpdate
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
async def test_new_exercise_defaults_to_not_reviewed(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    service = ExerciseService(db_session)
    read = await service.get_exercise_read(exercise.id)
    assert read.admin_reviewed is False


@pytest.mark.asyncio
async def test_update_toggles_admin_reviewed_without_touching_other_fields(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    service = ExerciseService(db_session)

    marked = await service.update_exercise(exercise.id, ExerciseUpdate(admin_reviewed=True))
    assert marked.admin_reviewed is True
    assert marked.name == exercise.name

    unmarked = await service.update_exercise(exercise.id, ExerciseUpdate(admin_reviewed=False))
    assert unmarked.admin_reviewed is False
