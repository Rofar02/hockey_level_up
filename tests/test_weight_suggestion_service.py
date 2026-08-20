"""WeightSuggestionService: first-time bodyweight-ratio formula vs.
history-based feedback adjustment, equipment-based rounding, and (Phase:
П.1 double progression) rep-range-aware feedback gating plus a detraining
discount for a stale last set.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.exercise import EquipmentItem, Exercise, ExerciseCategory, ExerciseEquipmentItem, ExerciseType, TrainingPhase
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
from app.models.user import FitnessTier, User
from app.services.weight_suggestion_service import (
    MACROCYCLE_DELOAD_WEIGHT_MULTIPLIER,
    WeightSuggestionService,
)


def _make_user(
    *, weight: float | None = 80.0, fitness_tier: FitnessTier | None = FitnessTier.INTERMEDIATE
) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"weight_{unique}",
        email=f"weight_{unique}@example.com",
        password_hash="irrelevant",
        weight=weight,
        fitness_tier=fitness_tier,
    )


def _make_exercise(
    db_session,
    *,
    tracks_weight: bool = True,
    bodyweight_ratio: float | None = 0.5,
    # Stage 2.2: rounding step is now a real per-item check (BARBELL ->
    # 2.5kg, everything else -> 1kg, see WeightSuggestionService) instead
    # of the old gym/home/bodyweight tier -- requires_barbell=True is the
    # default here to match every pre-2.2 test's implicit
    # equipment_type=EquipmentType.GYM default, only
    # test_home_equipment_rounds_to_nearest_kg below opts out.
    requires_barbell: bool = True,
    exercise_type: ExerciseType | None = None,
    rep_range_min: int | None = None,
    rep_range_max: int | None = None,
) -> Exercise:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=3,
        tracks_weight=tracks_weight,
        bodyweight_ratio=bodyweight_ratio,
        exercise_type=exercise_type,
        rep_range_min=rep_range_min,
        rep_range_max=rep_range_max,
    )
    db_session.add(exercise)
    if requires_barbell:
        db_session.add(
            ExerciseEquipmentItem(exercise_id=exercise.id, equipment_item=EquipmentItem.BARBELL)
        )
    return exercise


async def _make_set_history(
    db_session,
    user: User,
    exercise: Exercise,
    *,
    weight_kg: float,
    feedback: SetFeedback | None,
    reps_completed: int | None = None,
    completed_at: datetime | None = None,
) -> None:
    """A single prior SetCompletion for user+exercise, wired through a
    throwaway WeeklyPlan/DayPlan/TrainingSession chain to satisfy the FK."""
    session_block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0
    )
    day_plan = DayPlan(
        id=uuid.uuid4(),
        date=date.today(),
        session_type=DaySessionType.OFF_ICE,
        training_session=TrainingSession(id=uuid.uuid4(), blocks=[session_block]),
    )
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=date.today(), day_plans=[day_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    db_session.add(
        SetCompletion(
            id=uuid.uuid4(),
            user_id=user.id,
            exercise_id=exercise.id,
            training_session_id=day_plan.training_session.id,
            set_number=1,
            weight_kg=weight_kg,
            reps_completed=reps_completed,
            feedback=feedback,
            completed_at=completed_at if completed_at is not None else datetime.now(timezone.utc),
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
async def test_returns_none_when_exercise_does_not_track_weight(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(db_session, tracks_weight=False)
    db_session.add(user)
    await db_session.flush()

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    assert result is None


@pytest.mark.asyncio
async def test_first_time_uses_bodyweight_ratio_and_tier_multiplier(db_session) -> None:
    user = _make_user(weight=80.0, fitness_tier=FitnessTier.ADVANCED)
    exercise = _make_exercise(db_session, bodyweight_ratio=0.5)
    db_session.add(user)
    await db_session.flush()

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # 80 * 0.5 * 1.3 (advanced) = 52.0 -> nearest multiple of the gym's 2.5 step is 52.5
    assert result == 52.5


@pytest.mark.asyncio
async def test_missing_fitness_tier_defaults_to_intermediate(db_session) -> None:
    user = _make_user(weight=80.0, fitness_tier=None)
    exercise = _make_exercise(db_session, bodyweight_ratio=0.5)
    db_session.add(user)
    await db_session.flush()

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # 80 * 0.5 * 1.0 (intermediate default) = 40.0
    assert result == 40.0


@pytest.mark.asyncio
async def test_first_time_without_bodyweight_ratio_returns_none(db_session) -> None:
    user = _make_user(weight=80.0)
    exercise = _make_exercise(db_session, bodyweight_ratio=None)
    db_session.add(user)
    await db_session.flush()

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    assert result is None


@pytest.mark.asyncio
async def test_first_time_without_user_bodyweight_returns_none(db_session) -> None:
    user = _make_user(weight=None)
    exercise = _make_exercise(db_session)
    db_session.add(user)
    await db_session.flush()

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    assert result is None


@pytest.mark.asyncio
async def test_home_equipment_rounds_to_nearest_kg(db_session) -> None:
    user = _make_user(weight=70.0, fitness_tier=FitnessTier.BEGINNER)
    exercise = _make_exercise(db_session, bodyweight_ratio=0.4)
    db_session.add(user)
    await db_session.flush()

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # 70 * 0.4 * 0.7 (beginner) = 19.6 -> rounds to nearest 1kg = 20.0
    assert result == 20.0


@pytest.mark.parametrize(
    "feedback,expected",
    [
        (None, 40.0),  # no feedback recorded yet -> no adjustment
        (SetFeedback.EASY, 42.5),  # 40 * 1.05 = 42.0 -> nearest 2.5 = 42.5
        (SetFeedback.NORMAL, 40.0),  # 40 * 1.025 = 41.0 -> nearest 2.5 = 40.0
        (SetFeedback.HARD, 40.0),  # unchanged
        (SetFeedback.MAX, 37.5),  # 40 * 0.95 = 38.0 -> nearest 2.5 = 37.5
    ],
)
@pytest.mark.asyncio
async def test_history_adjusts_last_weight_by_feedback(
    db_session, feedback: SetFeedback | None, expected: float
) -> None:
    user = _make_user()
    exercise = _make_exercise(db_session)
    db_session.add(user)
    await db_session.flush()
    await _make_set_history(db_session, user, exercise, weight_kg=40.0, feedback=feedback)

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    assert result == expected


@pytest.mark.asyncio
async def test_history_takes_precedence_over_first_time_formula(db_session) -> None:
    """Once there's any history, the bodyweight-ratio formula is never used again."""
    user = _make_user(weight=80.0, fitness_tier=FitnessTier.ADVANCED)
    exercise = _make_exercise(db_session, bodyweight_ratio=0.5)
    db_session.add(user)
    await db_session.flush()
    await _make_set_history(db_session, user, exercise, weight_kg=10.0, feedback=SetFeedback.HARD)

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # If the formula were still used it'd be 52.5 (see the first-time test) --
    # instead it must come from the logged 10.0kg history.
    assert result == 10.0


# -- Phase: П.1 double progression -- rep-range-aware feedback gating --


@pytest.mark.asyncio
async def test_rep_range_exercise_hitting_top_with_good_feedback_grows_weight(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(db_session, 
        exercise_type=ExerciseType.SETS_REPS,
        rep_range_min=6,
        rep_range_max=12,
    )
    db_session.add(user)
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, weight_kg=40.0, feedback=SetFeedback.EASY, reps_completed=12
    )

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # Hit rep_range_max with easy feedback -> same 1.05 growth as the plain
    # (no rep range) case: 40 * 1.05 = 42.0 -> nearest 2.5 = 42.5
    assert result == 42.5


@pytest.mark.asyncio
async def test_rep_range_exercise_not_hitting_top_with_easy_feedback_does_not_grow_weight(
    db_session,
) -> None:
    """The one externally-visible behavior change for rep-range exercises:
    easy/normal feedback alone no longer grows weight -- RepsSuggestionService
    pushes reps up instead, until the range's ceiling is actually reached."""
    user = _make_user()
    exercise = _make_exercise(db_session, 
        exercise_type=ExerciseType.SETS_REPS,
        rep_range_min=6,
        rep_range_max=12,
    )
    db_session.add(user)
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, weight_kg=40.0, feedback=SetFeedback.EASY, reps_completed=8
    )

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    assert result == 40.0


@pytest.mark.asyncio
async def test_rep_range_exercise_max_feedback_still_reduces_weight(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(db_session, 
        exercise_type=ExerciseType.SETS_REPS,
        rep_range_min=6,
        rep_range_max=12,
    )
    db_session.add(user)
    await db_session.flush()
    await _make_set_history(
        db_session, user, exercise, weight_kg=40.0, feedback=SetFeedback.MAX, reps_completed=8
    )

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # MAX always backs weight off regardless of rep-range/hit-top status:
    # 40 * 0.95 = 38.0 -> nearest 2.5 = 37.5
    assert result == 37.5


# -- Phase: П.1 double progression -- detraining coefficient --


@pytest.mark.asyncio
async def test_recent_gap_does_not_apply_detraining_discount(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(db_session)
    db_session.add(user)
    await db_session.flush()
    await _make_set_history(
        db_session,
        user,
        exercise,
        weight_kg=40.0,
        feedback=None,
        completed_at=datetime.now(timezone.utc) - timedelta(weeks=3),
    )

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    assert result == 40.0


@pytest.mark.asyncio
async def test_four_to_seven_week_gap_applies_point_nine_detraining(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(db_session)
    db_session.add(user)
    await db_session.flush()
    await _make_set_history(
        db_session,
        user,
        exercise,
        weight_kg=40.0,
        feedback=None,
        completed_at=datetime.now(timezone.utc) - timedelta(weeks=5),
    )

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # 40 * 1.0 (no feedback) * 0.9 = 36.0 -> nearest 2.5 = 35.0
    assert result == 35.0


@pytest.mark.asyncio
async def test_eight_plus_week_gap_applies_point_eight_detraining(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(db_session)
    db_session.add(user)
    await db_session.flush()
    await _make_set_history(
        db_session,
        user,
        exercise,
        weight_kg=40.0,
        feedback=None,
        completed_at=datetime.now(timezone.utc) - timedelta(weeks=9),
    )

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # 40 * 1.0 (no feedback) * 0.8 = 32.0 -> nearest 2.5 = 32.5
    assert result == 32.5


@pytest.mark.asyncio
async def test_detraining_combines_multiplicatively_with_feedback_adjustment(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(db_session)
    db_session.add(user)
    await db_session.flush()
    await _make_set_history(
        db_session,
        user,
        exercise,
        weight_kg=40.0,
        feedback=SetFeedback.EASY,
        completed_at=datetime.now(timezone.utc) - timedelta(weeks=9),
    )

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # 40 * 1.05 (easy) * 0.8 (8+ week gap) = 33.6 -> nearest 2.5 = 32.5
    assert result == 32.5


# -- Phase: П.2 macrocycle deload --


@pytest.mark.asyncio
async def test_macrocycle_deload_floors_weight_ignoring_feedback(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(db_session)
    db_session.add(user)
    await db_session.flush()
    await _make_active_block(db_session, user, is_macrocycle_deload=True)
    # MAX feedback would normally reduce weight further (x0.95) -- the
    # macrocycle floor must win outright, not stack with it.
    await _make_set_history(db_session, user, exercise, weight_kg=40.0, feedback=SetFeedback.MAX)

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # 40 * 0.7 = 28.0 -> nearest 2.5 = 27.5
    assert MACROCYCLE_DELOAD_WEIGHT_MULTIPLIER == 0.7
    assert result == 27.5


@pytest.mark.asyncio
async def test_macrocycle_deload_ignores_detraining_discount(db_session) -> None:
    """A stale last set (would normally trigger the detraining discount)
    must not stack with the macrocycle floor -- the floor multiplier alone
    applies, not floor * detraining."""
    user = _make_user()
    exercise = _make_exercise(db_session)
    db_session.add(user)
    await db_session.flush()
    await _make_active_block(db_session, user, is_macrocycle_deload=True)
    await _make_set_history(
        db_session,
        user,
        exercise,
        weight_kg=40.0,
        feedback=None,
        completed_at=datetime.now(timezone.utc) - timedelta(weeks=9),
    )

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # 40 * 0.7 = 28.0 -> nearest 2.5 = 27.5 (not 40 * 0.7 * 0.8)
    assert result == 27.5


@pytest.mark.asyncio
async def test_macrocycle_deload_hitting_rep_range_top_does_not_grow_weight(db_session) -> None:
    """Even the rep-range-aware growth path (hit the ceiling with good
    feedback) is overridden by the macrocycle floor."""
    user = _make_user()
    exercise = _make_exercise(db_session, 
        exercise_type=ExerciseType.SETS_REPS,
        rep_range_min=6,
        rep_range_max=12,
    )
    db_session.add(user)
    await db_session.flush()
    await _make_active_block(db_session, user, is_macrocycle_deload=True)
    await _make_set_history(
        db_session, user, exercise, weight_kg=40.0, feedback=SetFeedback.EASY, reps_completed=12
    )

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    assert result == 27.5


@pytest.mark.asyncio
async def test_macrocycle_deload_does_not_affect_first_time_formula(db_session) -> None:
    """No history yet -- there's no accumulated weight to floor, so the
    normal bodyweight-ratio formula is unaffected by is_macrocycle_deload."""
    user = _make_user(weight=80.0, fitness_tier=FitnessTier.ADVANCED)
    exercise = _make_exercise(db_session, bodyweight_ratio=0.5)
    db_session.add(user)
    await db_session.flush()
    await _make_active_block(db_session, user, is_macrocycle_deload=True)

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # Same as test_first_time_uses_bodyweight_ratio_and_tier_multiplier
    assert result == 52.5


@pytest.mark.asyncio
async def test_non_macrocycle_deload_block_is_unaffected(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(db_session)
    db_session.add(user)
    await db_session.flush()
    await _make_active_block(db_session, user, is_macrocycle_deload=False)
    await _make_set_history(db_session, user, exercise, weight_kg=40.0, feedback=SetFeedback.EASY)

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # Normal feedback path (no rep range configured): 40 * 1.05 = 42.0 -> 42.5
    assert result == 42.5
