"""ExerciseRepository.list_for_assembly's UserTemporaryRestriction filter
(P3 item #7; extended 2026-08-27 with muscle_group): an exercise tagged
with an actively-restricted movement pattern OR muscle group is excluded
from assembly entirely -- every category (unlike the equipment filter just
above it in the same method, which skips ON_ICE -- a restriction applies
regardless of where the exercise happens), and even if the exercise also
carries an unrestricted pattern/group (whole-exercise exclusion, not
per-tag).
"""
import uuid
from datetime import date, timedelta

import pytest

from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseMuscleGroup,
    MovementPattern,
    MuscleGroup,
    TrainingPhase,
)
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.repositories.exercise_repository import ExerciseRepository


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"restrictgear_{unique}",
        email=f"restrictgear_{unique}@example.com",
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


def _restriction(user_id: uuid.UUID, pattern: MovementPattern, **overrides) -> UserTemporaryRestriction:
    defaults = dict(
        user_id=user_id, movement_pattern=pattern, expires_at=date.today() + timedelta(days=14)
    )
    defaults.update(overrides)
    return UserTemporaryRestriction(**defaults)


def _muscle_restriction(
    user_id: uuid.UUID, group: MuscleGroup, **overrides
) -> UserTemporaryRestriction:
    defaults = dict(
        user_id=user_id, movement_pattern=None, muscle_group=group,
        expires_at=date.today() + timedelta(days=14),
    )
    defaults.update(overrides)
    return UserTemporaryRestriction(**defaults)


@pytest.mark.asyncio
async def test_off_ice_exercise_with_restricted_pattern_is_excluded(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(category=ExerciseCategory.OFF_ICE)
    db_session.add_all([
        user,
        exercise,
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT),
        _restriction(user.id, MovementPattern.SQUAT),
    ])
    await db_session.flush()

    result = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=user, category=ExerciseCategory.OFF_ICE
    )

    assert exercise.id not in {e.id for e in result}


@pytest.mark.asyncio
async def test_on_ice_exercise_with_restricted_pattern_is_also_excluded(db_session) -> None:
    """Unlike the equipment filter (which never restricts ON_ICE), a
    restricted movement pattern excludes on-ice exercises too."""
    user = _make_user()
    exercise = _make_exercise(category=ExerciseCategory.ON_ICE)
    db_session.add_all([
        user,
        exercise,
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT),
        _restriction(user.id, MovementPattern.SQUAT),
    ])
    await db_session.flush()

    result = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=user, category=ExerciseCategory.ON_ICE
    )

    assert exercise.id not in {e.id for e in result}


@pytest.mark.asyncio
async def test_exercise_with_restricted_and_unrestricted_pattern_still_fully_excluded(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([
        user,
        exercise,
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.CORE),
        _restriction(user.id, MovementPattern.SQUAT),
    ])
    await db_session.flush()

    result = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=user, category=ExerciseCategory.OFF_ICE
    )

    assert exercise.id not in {e.id for e in result}


@pytest.mark.asyncio
async def test_unrestricted_pattern_exercise_is_unaffected(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([
        user,
        exercise,
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.CORE),
        _restriction(user.id, MovementPattern.SQUAT),
    ])
    await db_session.flush()

    result = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=user, category=ExerciseCategory.OFF_ICE
    )

    assert exercise.id in {e.id for e in result}


@pytest.mark.asyncio
async def test_expired_restriction_excludes_nothing(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([
        user,
        exercise,
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT),
        _restriction(user.id, MovementPattern.SQUAT, expires_at=date.today() - timedelta(days=1)),
    ])
    await db_session.flush()

    result = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=user, category=ExerciseCategory.OFF_ICE
    )

    assert exercise.id in {e.id for e in result}


@pytest.mark.asyncio
async def test_exercise_with_restricted_muscle_group_is_excluded(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(category=ExerciseCategory.OFF_ICE)
    db_session.add_all([
        user,
        exercise,
        ExerciseMuscleGroup(exercise_id=exercise.id, muscle_group=MuscleGroup.QUADS, weight=1.0),
        _muscle_restriction(user.id, MuscleGroup.QUADS),
    ])
    await db_session.flush()

    result = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=user, category=ExerciseCategory.OFF_ICE
    )

    assert exercise.id not in {e.id for e in result}


@pytest.mark.asyncio
async def test_on_ice_exercise_with_restricted_muscle_group_is_also_excluded(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(category=ExerciseCategory.ON_ICE)
    db_session.add_all([
        user,
        exercise,
        ExerciseMuscleGroup(exercise_id=exercise.id, muscle_group=MuscleGroup.QUADS, weight=1.0),
        _muscle_restriction(user.id, MuscleGroup.QUADS),
    ])
    await db_session.flush()

    result = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=user, category=ExerciseCategory.ON_ICE
    )

    assert exercise.id not in {e.id for e in result}


@pytest.mark.asyncio
async def test_unrestricted_muscle_group_exercise_is_unaffected(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([
        user,
        exercise,
        ExerciseMuscleGroup(exercise_id=exercise.id, muscle_group=MuscleGroup.CHEST, weight=1.0),
        _muscle_restriction(user.id, MuscleGroup.QUADS),
    ])
    await db_session.flush()

    result = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=user, category=ExerciseCategory.OFF_ICE
    )

    assert exercise.id in {e.id for e in result}


@pytest.mark.asyncio
async def test_pattern_and_muscle_group_restrictions_both_apply_independently(db_session) -> None:
    """A player can have one of each kind active at once -- each excludes
    its own matching exercises, neither interferes with the other."""
    user = _make_user()
    squat_exercise = _make_exercise(category=ExerciseCategory.OFF_ICE)
    chest_exercise = _make_exercise(category=ExerciseCategory.OFF_ICE)
    safe_exercise = _make_exercise(category=ExerciseCategory.OFF_ICE)
    db_session.add_all([
        user,
        squat_exercise,
        chest_exercise,
        safe_exercise,
        ExerciseMovementPattern(exercise_id=squat_exercise.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMuscleGroup(exercise_id=chest_exercise.id, muscle_group=MuscleGroup.CHEST, weight=1.0),
        _restriction(user.id, MovementPattern.SQUAT),
        _muscle_restriction(user.id, MuscleGroup.CHEST),
    ])
    await db_session.flush()

    result_ids = {
        e.id
        for e in await ExerciseRepository(db_session).list_for_assembly(
            phase=TrainingPhase.MAIN, user=user, category=ExerciseCategory.OFF_ICE
        )
    }

    assert squat_exercise.id not in result_ids
    assert chest_exercise.id not in result_ids
    assert safe_exercise.id in result_ids


@pytest.mark.asyncio
async def test_lifted_restriction_excludes_nothing(db_session) -> None:
    from datetime import datetime, timezone

    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([
        user,
        exercise,
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT),
        _restriction(user.id, MovementPattern.SQUAT, lifted_at=datetime.now(timezone.utc)),
    ])
    await db_session.flush()

    result = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=user, category=ExerciseCategory.OFF_ICE
    )

    assert exercise.id in {e.id for e in result}
