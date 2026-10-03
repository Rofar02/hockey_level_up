"""Time progression for timed strength holds (2026-10-03):
RepsSuggestionService.suggest_duration / is_duration_stuck_at_ceiling.
Same double-progression idea as suggest_reps, in seconds: +10/+5/0/-5 s by
feedback after a session held in full, the actually-held time (rounded down
to 5 s) after a round cut short, always within [target, 2 * target].
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseType,
    StimulusType,
    TrainingPhase,
)
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
from tests.dates import utc_today


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"hold_{unique}",
        email=f"hold_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise(
    *,
    target: int | None = 30,
    phase: TrainingPhase = TrainingPhase.MAIN,
    stimulus: StimulusType = StimulusType.STRENGTH,
    exercise_type: ExerciseType = ExerciseType.DURATION,
) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Hold {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=phase,
        difficulty_level=1,
        exercise_type=exercise_type,
        stimulus_type=stimulus,
        target_duration_seconds=target,
        target_sets=3,
        tracks_weight=False,
    )


async def _make_rounds(
    db_session,
    user: User,
    exercise: Exercise,
    *,
    seconds_per_round: list[int],
    feedback: SetFeedback | None,
    minutes_ago: int = 0,
) -> None:
    """One past session's rounds; feedback on the last one, as save_feedback stores it."""
    day_plan = DayPlan(
        id=uuid.uuid4(),
        date=utc_today(),
        session_type=DaySessionType.OFF_ICE,
        training_session=TrainingSession(
            id=uuid.uuid4(),
            blocks=[SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0)],
        ),
    )
    db_session.add(
        # one plan per (user, week) is unique -- older sessions go to older weeks
        WeeklyPlan(
            id=uuid.uuid4(),
            user_id=user.id,
            week_start_date=utc_today() - timedelta(weeks=minutes_ago),
            day_plans=[day_plan],
        )
    )
    await db_session.flush()
    base = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    for index, seconds in enumerate(seconds_per_round, start=1):
        db_session.add(
            SetCompletion(
                id=uuid.uuid4(),
                user_id=user.id,
                exercise_id=exercise.id,
                training_session_id=day_plan.training_session.id,
                set_number=index,
                duration_seconds_completed=seconds,
                feedback=feedback if index == len(seconds_per_round) else None,
                completed_at=base + timedelta(seconds=index),
            )
        )
    await db_session.flush()


async def _setup(db_session, **exercise_kwargs) -> tuple[User, Exercise]:
    user = _make_user()
    exercise = _make_exercise(**exercise_kwargs)
    db_session.add_all([user, exercise])
    await db_session.flush()
    return user, exercise


@pytest.mark.asyncio
async def test_first_time_gets_the_catalog_target(db_session) -> None:
    user, exercise = await _setup(db_session)
    assert await RepsSuggestionService(db_session).suggest_duration(user, exercise) == 30


@pytest.mark.parametrize(
    ("feedback", "expected"),
    [
        (SetFeedback.EASY, 45),
        (SetFeedback.NORMAL, 40),
        (SetFeedback.HARD, 35),
        (SetFeedback.MAX, 30),
        (None, 35),
    ],
)
@pytest.mark.asyncio
async def test_full_session_moves_by_feedback(db_session, feedback, expected) -> None:
    user, exercise = await _setup(db_session)
    await _make_rounds(db_session, user, exercise, seconds_per_round=[35, 35, 35], feedback=feedback)
    assert await RepsSuggestionService(db_session).suggest_duration(user, exercise) == expected


@pytest.mark.asyncio
async def test_round_cut_short_continues_from_what_was_held(db_session) -> None:
    user, exercise = await _setup(db_session)
    await _make_rounds(db_session, user, exercise, seconds_per_round=[45, 45, 38], feedback=SetFeedback.HARD)
    assert await RepsSuggestionService(db_session).suggest_duration(user, exercise) == 35


@pytest.mark.asyncio
async def test_never_below_the_start_value(db_session) -> None:
    user, exercise = await _setup(db_session)
    await _make_rounds(db_session, user, exercise, seconds_per_round=[30, 30, 12], feedback=SetFeedback.MAX)
    assert await RepsSuggestionService(db_session).suggest_duration(user, exercise) == 30


@pytest.mark.asyncio
async def test_never_above_twice_the_start_value(db_session) -> None:
    user, exercise = await _setup(db_session)
    await _make_rounds(db_session, user, exercise, seconds_per_round=[55, 55, 55], feedback=SetFeedback.EASY)
    assert await RepsSuggestionService(db_session).suggest_duration(user, exercise) == 60


@pytest.mark.asyncio
async def test_only_the_latest_session_counts(db_session) -> None:
    user, exercise = await _setup(db_session)
    await _make_rounds(db_session, user, exercise, seconds_per_round=[50, 50], feedback=SetFeedback.EASY, minutes_ago=60)
    await _make_rounds(db_session, user, exercise, seconds_per_round=[35, 35], feedback=SetFeedback.NORMAL)
    assert await RepsSuggestionService(db_session).suggest_duration(user, exercise) == 40


@pytest.mark.parametrize(
    "kwargs",
    [
        {"stimulus": StimulusType.ENDURANCE},
        {"stimulus": StimulusType.SKILL},
        {"stimulus": StimulusType.POWER},
        {"phase": TrainingPhase.WARMUP},
        {"phase": TrainingPhase.COOLDOWN},
        {"phase": TrainingPhase.PUCK},
        {"exercise_type": ExerciseType.SETS_REPS},
        {"target": None},
    ],
)
@pytest.mark.asyncio
async def test_no_time_progression_outside_main_strength_holds(db_session, kwargs) -> None:
    user, exercise = await _setup(db_session, **kwargs)
    service = RepsSuggestionService(db_session)
    assert await service.suggest_duration(user, exercise) is None
    assert await service.is_duration_stuck_at_ceiling(user, exercise) is False


@pytest.mark.asyncio
async def test_stuck_at_ceiling_only_when_full_ceiling_held_with_good_feedback(db_session) -> None:
    user, exercise = await _setup(db_session)
    service = RepsSuggestionService(db_session)
    assert await service.is_stuck_at_ceiling(user, exercise) is False

    await _make_rounds(db_session, user, exercise, seconds_per_round=[60, 60, 60], feedback=SetFeedback.HARD, minutes_ago=30)
    assert await service.is_stuck_at_ceiling(user, exercise) is False

    await _make_rounds(db_session, user, exercise, seconds_per_round=[60, 60, 55], feedback=SetFeedback.NORMAL, minutes_ago=20)
    assert await service.is_stuck_at_ceiling(user, exercise) is False

    await _make_rounds(db_session, user, exercise, seconds_per_round=[60, 60, 60], feedback=SetFeedback.NORMAL)
    # is_stuck_at_ceiling routes timed holds to the duration check, so the
    # scheduler's existing variant escalation picks them up unchanged.
    assert await service.is_stuck_at_ceiling(user, exercise) is True


@pytest.mark.asyncio
async def test_macrocycle_deload_goes_back_to_the_start_value(db_session) -> None:
    user, exercise = await _setup(db_session)
    await _make_rounds(db_session, user, exercise, seconds_per_round=[50, 50, 50], feedback=SetFeedback.EASY)
    db_session.add(
        TrainingBlock(user_id=user.id, block_number=4, phase=BlockPhase.ACCUMULATION, is_macrocycle_deload=True)
    )
    await db_session.flush()
    assert await RepsSuggestionService(db_session).suggest_duration(user, exercise) == 30
