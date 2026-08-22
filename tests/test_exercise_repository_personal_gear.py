"""ExerciseRepository.list_for_assembly's personal-gear split (2026-08-22).

Regression coverage for a real bug report ("клюшка открывается через
Зал"): has_gym_access=True used to bypass the equipment filter entirely,
so a hockey-stick-required exercise wrongly showed up for any gym-access
user even without a stick. PERSONAL_GEAR_ITEMS (app/models/exercise.py)
now excludes such items from the bypass -- a gym has dumbbells, but not a
personal hockey stick.
"""
import uuid

import pytest

from app.models.exercise import (
    EquipmentItem,
    Exercise,
    ExerciseCategory,
    ExerciseEquipmentItem,
    TrainingPhase,
    UserEquipmentItem,
)
from app.models.user import User
from app.repositories.exercise_repository import ExerciseRepository


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"gear_{unique}",
        email=f"gear_{unique}@example.com",
        password_hash="irrelevant",
        friend_code=unique.upper(),
        level=1,
    )
    defaults.update(overrides)
    return User(**defaults)


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


@pytest.mark.asyncio
async def test_gym_access_does_not_unlock_a_stick_required_exercise(db_session) -> None:
    gym_user = _make_user(has_gym_access=True)
    stick_exercise = _make_exercise()
    db_session.add_all([
        gym_user,
        stick_exercise,
        ExerciseEquipmentItem(
            exercise_id=stick_exercise.id, equipment_item=EquipmentItem.HOCKEY_STICK
        ),
    ])
    await db_session.flush()

    candidates = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=gym_user, category=ExerciseCategory.OFF_ICE
    )

    assert stick_exercise.id not in {e.id for e in candidates}


@pytest.mark.asyncio
async def test_owning_a_stick_unlocks_it_even_with_gym_access(db_session) -> None:
    gym_user = _make_user(has_gym_access=True)
    db_session.add(gym_user)
    await db_session.flush()
    stick_exercise = _make_exercise()
    db_session.add_all([
        stick_exercise,
        ExerciseEquipmentItem(
            exercise_id=stick_exercise.id, equipment_item=EquipmentItem.HOCKEY_STICK
        ),
        UserEquipmentItem(user_id=gym_user.id, equipment_item=EquipmentItem.HOCKEY_STICK),
    ])
    await db_session.flush()

    candidates = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=gym_user, category=ExerciseCategory.OFF_ICE
    )

    assert stick_exercise.id in {e.id for e in candidates}


@pytest.mark.asyncio
async def test_gym_access_still_unlocks_ordinary_gym_equipment(db_session) -> None:
    """Not a regression for every other item -- barbell stays bypass-eligible,
    only the hand-picked PERSONAL_GEAR_ITEMS set is excluded."""
    gym_user = _make_user(has_gym_access=True)
    barbell_exercise = _make_exercise()
    db_session.add_all([
        gym_user,
        barbell_exercise,
        ExerciseEquipmentItem(exercise_id=barbell_exercise.id, equipment_item=EquipmentItem.BARBELL),
    ])
    await db_session.flush()

    candidates = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=gym_user, category=ExerciseCategory.OFF_ICE
    )

    assert barbell_exercise.id in {e.id for e in candidates}


@pytest.mark.asyncio
async def test_no_gym_access_still_requires_owning_the_stick(db_session) -> None:
    bodyweight_user = _make_user(has_gym_access=False)
    stick_exercise = _make_exercise()
    db_session.add_all([
        bodyweight_user,
        stick_exercise,
        ExerciseEquipmentItem(
            exercise_id=stick_exercise.id, equipment_item=EquipmentItem.HOCKEY_STICK
        ),
    ])
    await db_session.flush()

    candidates = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=bodyweight_user, category=ExerciseCategory.OFF_ICE
    )

    assert stick_exercise.id not in {e.id for e in candidates}
