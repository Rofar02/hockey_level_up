"""RepsSuggestionService: double progression (Phase: П.1) for
exercise_type=sets_reps exercises. First-ever suggestion starts at
rep_range_min; hitting rep_range_max on every set of the last session with
good feedback resets to rep_range_min (weight grows instead, see
test_weight_suggestion_service.py); otherwise reps bump by a
feedback-scaled amount, clamped to the configured range.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.exercise import Exercise, ExerciseCategory, ExerciseType, TrainingPhase
from app.models.schedule import (
    BlockPhase,
    DayPlan,
    DaySessionType,
    SessionBlock,
    TrainingBlock,
    TrainingSession,
    WeeklyPlan,
)
from app.models.set_completion import SetCompletion, SetFeedback
from app.models.user import User
from app.services.reps_suggestion_service import RepsSuggestionService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"reps_{unique}",
        email=f"reps_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise(
    *,
    exercise_type: ExerciseType | None = ExerciseType.SETS_REPS,
    rep_range_min: int | None = 6,
    rep_range_max: int | None = 12,
) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=3,
        exercise_type=exercise_type,
        rep_range_min=rep_range_min,
        rep_range_max=rep_range_max,
    )


async def _make_set_history(
    db_session,
    user: User,
    exercise: Exercise,
    *,
    reps_per_set: list[int | None],
    last_set_feedback: SetFeedback | None,
) -> None:
    """One prior TrainingSession's worth of SetCompletion rows for
    user+exercise -- feedback only ever lands on the last row, matching
    SetCompletionService.save_feedback's real behavior."""
    blocks = [
        SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0)
    ]
    day_plan = DayPlan(
        id=uuid.uuid4(),
        date=date.today(),
        session_type=DaySessionType.OFF_ICE,
        training_session=TrainingSession(id=uuid.uuid4(), blocks=blocks),
    )
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=date.today(), day_plans=[day_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    training_session_id = day_plan.training_session.id
    # Explicitly staggered, not datetime.now() per row -- get_last_for_user_
    # exercise orders by completed_at DESC, and several rows created in a
    # tight loop can land on the same wall-clock tick (observed on Windows),
    # making "last" ambiguous. Strictly increasing timestamps guarantee
    # set_number order matches completed_at order, same intent as
    # test_training_block_progression.py's _Clock helper.
    base = datetime.now(timezone.utc)
    for index, reps in enumerate(reps_per_set, start=1):
        is_last = index == len(reps_per_set)
        db_session.add(
            SetCompletion(
                id=uuid.uuid4(),
                user_id=user.id,
                exercise_id=exercise.id,
                training_session_id=training_session_id,
                set_number=index,
                reps_completed=reps,
                feedback=last_set_feedback if is_last else None,
                completed_at=base + timedelta(seconds=index),
            )
        )
    await db_session.flush()


async def _make_active_block(
    db_session, user: User, *, is_macrocycle_deload: bool, block_number: int = 4
) -> None:
    db_session.add(
        TrainingBlock(
            user_id=user.id,
            block_number=block_number,
            phase=BlockPhase.ACCUMULATION,
            is_macrocycle_deload=is_macrocycle_deload,
        )
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_returns_none_when_exercise_type_is_not_sets_reps(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(exercise_type=ExerciseType.DURATION)
    db_session.add_all([user, exercise])
    await db_session.flush()

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    assert result is None


@pytest.mark.asyncio
async def test_returns_none_when_rep_range_not_backfilled(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=None, rep_range_max=None)
    db_session.add_all([user, exercise])
    await db_session.flush()

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    assert result is None


@pytest.mark.asyncio
async def test_first_time_starts_at_range_minimum(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=6, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    assert result == 6


@pytest.mark.asyncio
async def test_hitting_top_of_range_with_easy_feedback_resets_to_minimum(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=6, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[12, 12, 12], last_set_feedback=SetFeedback.EASY
    )

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    assert result == 6


@pytest.mark.asyncio
async def test_hitting_top_of_range_with_normal_feedback_resets_to_minimum(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=6, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[12, 12], last_set_feedback=SetFeedback.NORMAL
    )

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    assert result == 6


@pytest.mark.asyncio
async def test_hitting_top_of_range_with_hard_feedback_does_not_reset(db_session) -> None:
    """Hit the ceiling, but it felt hard -- not the "ready to add weight"
    signal, so reps still just bump instead of resetting."""
    user = _make_user()
    exercise = _make_exercise(rep_range_min=6, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[12, 12], last_set_feedback=SetFeedback.HARD
    )

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    # bump=1 for HARD, clamped to rep_range_max=12
    assert result == 12


@pytest.mark.asyncio
async def test_not_hitting_top_with_easy_feedback_bumps_by_two(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=6, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[8], last_set_feedback=SetFeedback.EASY
    )

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    assert result == 10


@pytest.mark.asyncio
async def test_not_hitting_top_with_hard_feedback_bumps_by_one(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=6, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[8], last_set_feedback=SetFeedback.HARD
    )

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    assert result == 9


@pytest.mark.asyncio
async def test_max_feedback_does_not_push_reps_further(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=6, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[8], last_set_feedback=SetFeedback.MAX
    )

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    assert result == 8


@pytest.mark.asyncio
async def test_no_feedback_recorded_yet_bumps_by_one(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=6, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[8], last_set_feedback=None
    )

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    assert result == 9


@pytest.mark.asyncio
async def test_bump_is_clamped_to_range_maximum(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=6, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[11], last_set_feedback=SetFeedback.EASY
    )

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    # 11 + 2 = 13, clamped to rep_range_max=12
    assert result == 12


@pytest.mark.asyncio
async def test_missing_reps_completed_falls_back_to_range_minimum(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=6, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[None], last_set_feedback=SetFeedback.EASY
    )

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    assert result == 6


# -- Phase: П.2 macrocycle deload --


@pytest.mark.asyncio
async def test_macrocycle_deload_floors_reps_ignoring_history_and_feedback(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=6, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_active_block(db_session, user, is_macrocycle_deload=True)
    # Would normally bump toward the ceiling on good feedback -- the
    # macrocycle floor must win outright, not stack with the bump.
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[11], last_set_feedback=SetFeedback.EASY
    )

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    assert result == 6


@pytest.mark.asyncio
async def test_macrocycle_deload_floors_reps_with_no_history_at_all(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=6, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_active_block(db_session, user, is_macrocycle_deload=True)

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    assert result == 6


@pytest.mark.asyncio
async def test_non_macrocycle_deload_block_is_unaffected(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=6, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_active_block(db_session, user, is_macrocycle_deload=False)
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[11], last_set_feedback=SetFeedback.EASY
    )

    result = await RepsSuggestionService(db_session).suggest_reps(user, exercise)

    # Normal bump path: 11 + 2 = 13, clamped to rep_range_max=12
    assert result == 12
