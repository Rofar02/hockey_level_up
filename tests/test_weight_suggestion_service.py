"""WeightSuggestionService: first-time bodyweight-ratio formula vs.
history-based feedback adjustment, and equipment-based rounding.
"""
import uuid
from datetime import date, datetime, timezone

import pytest

from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TargetStat, TrainingPhase
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion, SetFeedback
from app.models.user import FitnessTier, User
from app.services.weight_suggestion_service import WeightSuggestionService


def _make_user(
    *, weight: float | None = 80.0, fitness_tier: FitnessTier | None = FitnessTier.INTERMEDIATE
) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"weight_{unique}",
        email=f"weight_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        weight=weight,
        fitness_tier=fitness_tier,
    )


def _make_exercise(
    *,
    tracks_weight: bool = True,
    bodyweight_ratio: float | None = 0.5,
    equipment_type: EquipmentType = EquipmentType.GYM,
) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        target_stat=TargetStat.STRENGTH,
        difficulty_level=3,
        equipment_type=equipment_type,
        tracks_weight=tracks_weight,
        bodyweight_ratio=bodyweight_ratio,
    )


async def _make_set_history(
    db_session, user: User, exercise: Exercise, *, weight_kg: float, feedback: SetFeedback | None
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
            feedback=feedback,
            completed_at=datetime.now(timezone.utc),
        )
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_returns_none_when_exercise_does_not_track_weight(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise(tracks_weight=False)
    db_session.add_all([user, exercise])
    await db_session.flush()

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    assert result is None


@pytest.mark.asyncio
async def test_first_time_uses_bodyweight_ratio_and_tier_multiplier(db_session) -> None:
    user = _make_user(weight=80.0, fitness_tier=FitnessTier.ADVANCED)
    exercise = _make_exercise(bodyweight_ratio=0.5, equipment_type=EquipmentType.GYM)
    db_session.add_all([user, exercise])
    await db_session.flush()

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # 80 * 0.5 * 1.3 (advanced) = 52.0 -> nearest multiple of the gym's 2.5 step is 52.5
    assert result == 52.5


@pytest.mark.asyncio
async def test_missing_fitness_tier_defaults_to_intermediate(db_session) -> None:
    user = _make_user(weight=80.0, fitness_tier=None)
    exercise = _make_exercise(bodyweight_ratio=0.5, equipment_type=EquipmentType.GYM)
    db_session.add_all([user, exercise])
    await db_session.flush()

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # 80 * 0.5 * 1.0 (intermediate default) = 40.0
    assert result == 40.0


@pytest.mark.asyncio
async def test_first_time_without_bodyweight_ratio_returns_none(db_session) -> None:
    user = _make_user(weight=80.0)
    exercise = _make_exercise(bodyweight_ratio=None)
    db_session.add_all([user, exercise])
    await db_session.flush()

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    assert result is None


@pytest.mark.asyncio
async def test_first_time_without_user_bodyweight_returns_none(db_session) -> None:
    user = _make_user(weight=None)
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    assert result is None


@pytest.mark.asyncio
async def test_home_equipment_rounds_to_nearest_kg(db_session) -> None:
    user = _make_user(weight=70.0, fitness_tier=FitnessTier.BEGINNER)
    exercise = _make_exercise(bodyweight_ratio=0.4, equipment_type=EquipmentType.HOME)
    db_session.add_all([user, exercise])
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
    exercise = _make_exercise(equipment_type=EquipmentType.GYM)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(db_session, user, exercise, weight_kg=40.0, feedback=feedback)

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    assert result == expected


@pytest.mark.asyncio
async def test_history_takes_precedence_over_first_time_formula(db_session) -> None:
    """Once there's any history, the bodyweight-ratio formula is never used again."""
    user = _make_user(weight=80.0, fitness_tier=FitnessTier.ADVANCED)
    exercise = _make_exercise(bodyweight_ratio=0.5, equipment_type=EquipmentType.GYM)
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _make_set_history(db_session, user, exercise, weight_kg=10.0, feedback=SetFeedback.HARD)

    result = await WeightSuggestionService(db_session).suggest_weight(user, exercise)

    # If the formula were still used it'd be 52.5 (see the first-time test) --
    # instead it must come from the logged 10.0kg history.
    assert result == 10.0
