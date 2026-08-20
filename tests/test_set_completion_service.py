"""SetCompletionService: per-set logging layered on top of SessionBlock.

Covers ownership/membership validation, the server-computed suggested
weight (never trusted from the client), the >3x sanity-check guard against a
typo'd weight, was_weight_adjusted_manually bookkeeping, resubmission of the
same set overwriting in place, and the separate once-per-exercise feedback
endpoint. Does not touch block_completed/stat_consumer/xp_consumer at all --
those stay driven purely by SessionBlock.completed_at.
"""
import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.exercise import Exercise, ExerciseCategory, TrainingPhase
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion, SetFeedback
from app.models.user import FitnessTier, User
from app.services.set_completion_service import SetCompletionService


def _make_user(*, weight: float | None = 80.0) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"setlog_{unique}",
        email=f"setlog_{unique}@example.com",
        password_hash="irrelevant",
        has_gym_access=True,
        weight=weight,
        fitness_tier=FitnessTier.INTERMEDIATE,
    )


def _make_exercise(
    *, tracks_weight: bool = True, bodyweight_ratio: float | None = 0.5
) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=3,
        tracks_weight=tracks_weight,
        bodyweight_ratio=bodyweight_ratio,
    )


async def _make_session_with_block(db_session, user: User, exercise: Exercise) -> TrainingSession:
    session_block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0
    )
    training_session = TrainingSession(id=uuid.uuid4(), blocks=[session_block])
    day_plan = DayPlan(
        id=uuid.uuid4(),
        date=date.today(),
        session_type=DaySessionType.OFF_ICE,
        training_session=training_session,
    )
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=date.today(), day_plans=[day_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()
    return training_session


@pytest.mark.asyncio
async def test_save_set_uses_server_computed_suggestion_not_manual(db_session) -> None:
    user = _make_user(weight=80.0)  # intermediate tier -> 80 * 0.5 * 1.0 = 40.0
    exercise = _make_exercise(bodyweight_ratio=0.5)
    db_session.add_all([user, exercise])
    await db_session.flush()
    training_session = await _make_session_with_block(db_session, user, exercise)

    result = await SetCompletionService(db_session).save_set(
        user=user,
        exercise_id=exercise.id,
        training_session_id=training_session.id,
        set_number=1,
        weight_kg=40.0,
        reps_completed=8,
        duration_seconds_completed=None,
    )

    assert result.suggested_weight_kg == 40.0
    assert result.weight_kg == 40.0
    assert result.was_weight_adjusted_manually is False


@pytest.mark.asyncio
async def test_save_set_flags_manual_adjustment_when_weight_differs(db_session) -> None:
    user = _make_user(weight=80.0)
    exercise = _make_exercise(bodyweight_ratio=0.5)
    db_session.add_all([user, exercise])
    await db_session.flush()
    training_session = await _make_session_with_block(db_session, user, exercise)

    result = await SetCompletionService(db_session).save_set(
        user=user,
        exercise_id=exercise.id,
        training_session_id=training_session.id,
        set_number=1,
        weight_kg=45.0,  # suggestion is 40.0
        reps_completed=8,
        duration_seconds_completed=None,
    )

    assert result.suggested_weight_kg == 40.0
    assert result.weight_kg == 45.0
    assert result.was_weight_adjusted_manually is True


@pytest.mark.asyncio
async def test_save_set_rejects_weight_more_than_3x_suggested(db_session) -> None:
    user = _make_user(weight=80.0)
    exercise = _make_exercise(bodyweight_ratio=0.5)  # suggestion = 40.0
    db_session.add_all([user, exercise])
    await db_session.flush()
    training_session = await _make_session_with_block(db_session, user, exercise)

    with pytest.raises(HTTPException) as exc_info:
        await SetCompletionService(db_session).save_set(
            user=user,
            exercise_id=exercise.id,
            training_session_id=training_session.id,
            set_number=1,
            weight_kg=500.0,  # typo for 50
            reps_completed=8,
            duration_seconds_completed=None,
        )

    assert exc_info.value.status_code == 400

    # Rejected -- nothing silently clamped or persisted.
    rows = (
        await db_session.execute(
            select(SetCompletion).where(SetCompletion.training_session_id == training_session.id)
        )
    ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_save_set_requires_positive_weight_for_tracking_exercise(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    training_session = await _make_session_with_block(db_session, user, exercise)

    with pytest.raises(HTTPException) as exc_info:
        await SetCompletionService(db_session).save_set(
            user=user,
            exercise_id=exercise.id,
            training_session_id=training_session.id,
            set_number=1,
            weight_kg=None,
            reps_completed=8,
            duration_seconds_completed=None,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_save_set_rejects_exercise_not_in_session(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    other_exercise = _make_exercise()
    db_session.add_all([user, exercise, other_exercise])
    await db_session.flush()
    training_session = await _make_session_with_block(db_session, user, exercise)

    with pytest.raises(HTTPException) as exc_info:
        await SetCompletionService(db_session).save_set(
            user=user,
            exercise_id=other_exercise.id,  # not part of this session
            training_session_id=training_session.id,
            set_number=1,
            weight_kg=40.0,
            reps_completed=8,
            duration_seconds_completed=None,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_save_set_rejects_session_owned_by_another_user(db_session) -> None:
    owner = _make_user()
    intruder = _make_user()
    exercise = _make_exercise()
    db_session.add_all([owner, intruder, exercise])
    await db_session.flush()
    training_session = await _make_session_with_block(db_session, owner, exercise)

    with pytest.raises(HTTPException) as exc_info:
        await SetCompletionService(db_session).save_set(
            user=intruder,
            exercise_id=exercise.id,
            training_session_id=training_session.id,
            set_number=1,
            weight_kg=40.0,
            reps_completed=8,
            duration_seconds_completed=None,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_resubmitting_same_set_overwrites_in_place(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    training_session = await _make_session_with_block(db_session, user, exercise)

    service = SetCompletionService(db_session)
    first = await service.save_set(
        user=user,
        exercise_id=exercise.id,
        training_session_id=training_session.id,
        set_number=1,
        weight_kg=40.0,
        reps_completed=6,
        duration_seconds_completed=None,
    )
    second = await service.save_set(
        user=user,
        exercise_id=exercise.id,
        training_session_id=training_session.id,
        set_number=1,
        weight_kg=40.0,
        reps_completed=8,  # corrected
        duration_seconds_completed=None,
    )

    assert first.id == second.id
    assert second.reps_completed == 8

    rows = (
        await db_session.execute(
            select(SetCompletion).where(SetCompletion.training_session_id == training_session.id)
        )
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_save_feedback_sets_it_on_the_last_logged_set(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    training_session = await _make_session_with_block(db_session, user, exercise)

    service = SetCompletionService(db_session)
    await service.save_set(
        user=user,
        exercise_id=exercise.id,
        training_session_id=training_session.id,
        set_number=1,
        weight_kg=40.0,
        reps_completed=8,
        duration_seconds_completed=None,
    )
    set_two = await service.save_set(
        user=user,
        exercise_id=exercise.id,
        training_session_id=training_session.id,
        set_number=2,
        weight_kg=40.0,
        reps_completed=6,
        duration_seconds_completed=None,
    )

    result = await service.save_feedback(
        user=user,
        exercise_id=exercise.id,
        training_session_id=training_session.id,
        feedback=SetFeedback.HARD,
    )

    assert result.id == set_two.id  # highest set_number, not the first
    assert result.feedback == SetFeedback.HARD

    set_one = await db_session.get(SetCompletion, set_two.id)
    assert set_one is not None  # sanity: row actually persisted


@pytest.mark.asyncio
async def test_save_feedback_without_any_sets_raises_404(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    training_session = await _make_session_with_block(db_session, user, exercise)

    with pytest.raises(HTTPException) as exc_info:
        await SetCompletionService(db_session).save_feedback(
            user=user,
            exercise_id=exercise.id,
            training_session_id=training_session.id,
            feedback=SetFeedback.EASY,
        )

    assert exc_info.value.status_code == 404


# --- list_sets (GET /training-sessions/{id}/exercises/{id}/sets) ---


@pytest.mark.asyncio
async def test_list_sets_rejects_session_owned_by_another_user(db_session) -> None:
    owner = _make_user()
    intruder = _make_user()
    exercise = _make_exercise()
    db_session.add_all([owner, intruder, exercise])
    await db_session.flush()
    training_session = await _make_session_with_block(db_session, owner, exercise)

    with pytest.raises(HTTPException) as exc_info:
        await SetCompletionService(db_session).list_sets(
            user=intruder,
            exercise_id=exercise.id,
            training_session_id=training_session.id,
        )

    # Same ownership check as save_set/save_feedback -- 404, not 403, so an
    # intruder can't distinguish "not yours" from "doesn't exist".
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_sets_returns_empty_list_when_none_logged(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    training_session = await _make_session_with_block(db_session, user, exercise)

    result = await SetCompletionService(db_session).list_sets(
        user=user,
        exercise_id=exercise.id,
        training_session_id=training_session.id,
    )

    assert result == []


@pytest.mark.asyncio
async def test_list_sets_returns_sets_ordered_with_feedback_on_its_row(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    training_session = await _make_session_with_block(db_session, user, exercise)

    service = SetCompletionService(db_session)
    # Save out of order to prove the result comes back sorted by set_number,
    # not insertion order.
    await service.save_set(
        user=user,
        exercise_id=exercise.id,
        training_session_id=training_session.id,
        set_number=2,
        weight_kg=42.5,
        reps_completed=6,
        duration_seconds_completed=None,
    )
    await service.save_set(
        user=user,
        exercise_id=exercise.id,
        training_session_id=training_session.id,
        set_number=1,
        weight_kg=40.0,
        reps_completed=8,
        duration_seconds_completed=None,
    )
    await service.save_feedback(
        user=user,
        exercise_id=exercise.id,
        training_session_id=training_session.id,
        feedback=SetFeedback.NORMAL,
    )

    result = await service.list_sets(
        user=user,
        exercise_id=exercise.id,
        training_session_id=training_session.id,
    )

    assert [s.set_number for s in result] == [1, 2]
    assert result[0].weight_kg == 40.0
    assert result[0].reps_completed == 8
    assert result[1].weight_kg == 42.5
    assert result[1].reps_completed == 6

    # Feedback lands on set 2 -- it was the highest set_number logged at the
    # time save_feedback ran (see get_last_in_session_for_exercise).
    assert result[1].feedback == SetFeedback.NORMAL
    assert result[0].feedback is None
