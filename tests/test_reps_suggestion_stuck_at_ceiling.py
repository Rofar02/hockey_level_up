"""Stage 2.6 (2026-08-20 planning session): RepsSuggestionService.
is_stuck_at_ceiling -- the standalone signal ScheduleService._pick_main
uses to decide whether a tracks_weight=false exercise's variant pin should
be broken early for a harder same-pattern candidate (see
test_pick_main_bodyweight_escalation.py for that integration). Same
hit-the-top + good-feedback condition as suggest_reps's own reset branch
(test_reps_suggestion_service.py), just exposed as a bool instead of being
folded into a reps number.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.exercise import Exercise, ExerciseCategory, ExerciseType, TrainingPhase
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion, SetFeedback
from app.models.user import User
from app.services.reps_suggestion_service import RepsSuggestionService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"stuck_{unique}",
        email=f"stuck_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise(
    *,
    exercise_type: ExerciseType | None = ExerciseType.SETS_REPS,
    rep_range_min: int | None = 8,
    rep_range_max: int | None = 12,
) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        exercise_type=exercise_type,
        rep_range_min=rep_range_min,
        rep_range_max=rep_range_max,
        tracks_weight=False,
    )


async def _make_set_history(
    db_session,
    user: User,
    exercise: Exercise,
    *,
    reps_per_set: list[int | None],
    last_set_feedback: SetFeedback | None,
) -> None:
    """Mirrors test_reps_suggestion_service.py's helper of the same name --
    one prior TrainingSession's worth of SetCompletion rows, feedback only
    on the last row."""
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


@pytest.mark.asyncio
async def test_false_when_no_rep_range_configured(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=None, rep_range_max=None)
    db_session.add_all([user, exercise])
    await db_session.flush()

    assert await RepsSuggestionService(db_session).is_stuck_at_ceiling(user, exercise) is False


@pytest.mark.asyncio
async def test_false_on_first_ever_attempt(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()

    assert await RepsSuggestionService(db_session).is_stuck_at_ceiling(user, exercise) is False


@pytest.mark.asyncio
async def test_true_when_hit_top_with_good_feedback(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=8, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[12, 12, 12], last_set_feedback=SetFeedback.NORMAL
    )

    assert await RepsSuggestionService(db_session).is_stuck_at_ceiling(user, exercise) is True


@pytest.mark.asyncio
async def test_false_when_top_hit_but_feedback_was_hard(db_session) -> None:
    """Ceiling reached, but it felt hard -- not the "easy win, needs a
    harder version" signal, so no escalation should be triggered."""
    user = _make_user()
    exercise = _make_exercise(rep_range_min=8, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[12, 12, 12], last_set_feedback=SetFeedback.HARD
    )

    assert await RepsSuggestionService(db_session).is_stuck_at_ceiling(user, exercise) is False


@pytest.mark.asyncio
async def test_false_when_not_every_set_hit_the_top(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(rep_range_min=8, rep_range_max=12)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, reps_per_set=[12, 10, 12], last_set_feedback=SetFeedback.NORMAL
    )

    assert await RepsSuggestionService(db_session).is_stuck_at_ceiling(user, exercise) is False
