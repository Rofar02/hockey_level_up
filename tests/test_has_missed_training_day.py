"""has_missed_training_day (app/services/streak_service.py) and its use in
ProgressService.get_streak for a lazy, read-time recompute.

has_missed_training_day answers "is there a planned on/off-ice day, strictly
between two dates, that has no completed SessionBlock". A date with no
DayPlan at all, or a DayPlan with session_type=REST, must never count as
missed -- only a day the plan actually scheduled training for, and that
training never happened, counts.

get_streak must reflect a break the moment it's read, even though the
TrainingStreak row itself is only ever written by streak_consumer on the
next block_completed (see test_streak_consumer_day_plan.py for the write
side). The response-only current_streak=0 here is never persisted --
asserted below by re-reading the raw row afterwards.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TrainingPhase
from app.models.progress import TrainingStreak
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.user import User
from app.repositories.progress_repository import ProgressRepository
from app.services.progress_service import ProgressService
from app.services.streak_service import has_missed_training_day

TODAY = date(2026, 3, 10)
YESTERDAY = TODAY - timedelta(days=1)
TWO_DAYS_AGO = TODAY - timedelta(days=2)
THREE_DAYS_AGO = TODAY - timedelta(days=3)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"streak_{unique}",
        email=f"streak_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise() -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=3,
        equipment_type=EquipmentType.GYM,
    )


async def _add_day_plan(
    db_session, user_id: uuid.UUID, *, day_date: date, session_type: DaySessionType
) -> DayPlan:
    # week_start_date only needs to be unique per (user_id, week_start_date);
    # using the day's own date keeps each seeded DayPlan in its own WeeklyPlan
    # without worrying about real calendar-week boundaries.
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user_id, week_start_date=day_date)
    db_session.add(weekly_plan)
    await db_session.flush()
    day_plan = DayPlan(
        id=uuid.uuid4(), weekly_plan_id=weekly_plan.id, date=day_date, session_type=session_type
    )
    db_session.add(day_plan)
    await db_session.flush()
    return day_plan


async def _add_completed_block(db_session, day_plan: DayPlan, exercise: Exercise) -> None:
    block = SessionBlock(
        id=uuid.uuid4(),
        phase=TrainingPhase.MAIN,
        exercise_id=exercise.id,
        order=0,
        completed_at=datetime.now(timezone.utc),
    )
    training_session = TrainingSession(id=uuid.uuid4(), day_plan_id=day_plan.id, blocks=[block])
    db_session.add(training_session)
    await db_session.flush()


# --- has_missed_training_day ---


@pytest.mark.asyncio
async def test_no_dates_strictly_between_is_never_missed(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    assert (
        await has_missed_training_day(db_session, user.id, YESTERDAY, TODAY) is False
    )
    assert (
        await has_missed_training_day(db_session, user.id, TODAY, TODAY) is False
    )


@pytest.mark.asyncio
async def test_rest_day_between_does_not_count_as_missed(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    await _add_day_plan(db_session, user.id, day_date=YESTERDAY, session_type=DaySessionType.REST)

    assert await has_missed_training_day(db_session, user.id, TWO_DAYS_AGO, TODAY) is False


@pytest.mark.asyncio
async def test_game_day_between_does_not_count_as_missed(db_session) -> None:
    # GAME is a light pre-game day, not a workout -- same non-breaking
    # treatment as REST (see ScheduleService._build_game_day_session).
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    await _add_day_plan(db_session, user.id, day_date=YESTERDAY, session_type=DaySessionType.GAME)

    assert await has_missed_training_day(db_session, user.id, TWO_DAYS_AGO, TODAY) is False


@pytest.mark.asyncio
async def test_missing_day_plan_does_not_count_as_missed(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    # No DayPlan at all for YESTERDAY.

    assert await has_missed_training_day(db_session, user.id, TWO_DAYS_AGO, TODAY) is False


@pytest.mark.asyncio
async def test_planned_training_day_without_completed_block_is_missed(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    await _add_day_plan(db_session, user.id, day_date=YESTERDAY, session_type=DaySessionType.ON_ICE)

    assert await has_missed_training_day(db_session, user.id, TWO_DAYS_AGO, TODAY) is True


@pytest.mark.asyncio
async def test_planned_training_day_with_incomplete_block_is_missed(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    day_plan = await _add_day_plan(
        db_session, user.id, day_date=YESTERDAY, session_type=DaySessionType.OFF_ICE
    )
    block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0
    )  # completed_at left None
    training_session = TrainingSession(id=uuid.uuid4(), day_plan_id=day_plan.id, blocks=[block])
    db_session.add(training_session)
    await db_session.flush()

    assert await has_missed_training_day(db_session, user.id, TWO_DAYS_AGO, TODAY) is True


@pytest.mark.asyncio
async def test_planned_training_day_with_completed_block_is_not_missed(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    day_plan = await _add_day_plan(
        db_session, user.id, day_date=YESTERDAY, session_type=DaySessionType.ON_ICE
    )
    await _add_completed_block(db_session, day_plan, exercise)

    assert await has_missed_training_day(db_session, user.id, TWO_DAYS_AGO, TODAY) is False


@pytest.mark.asyncio
async def test_other_users_day_plans_are_not_considered(db_session) -> None:
    user = _make_user()
    other_user = _make_user()
    db_session.add_all([user, other_user])
    await db_session.flush()
    # Missed training day, but it belongs to a different user.
    await _add_day_plan(
        db_session, other_user.id, day_date=YESTERDAY, session_type=DaySessionType.ON_ICE
    )

    assert await has_missed_training_day(db_session, user.id, TWO_DAYS_AGO, TODAY) is False


# --- ProgressService.get_streak (lazy read-time recompute) ---


async def _seed_streak(
    db_session, user_id: uuid.UUID, *, current_streak: int, longest_streak: int, last_activity_date: date
) -> None:
    db_session.add(
        TrainingStreak(
            id=uuid.uuid4(),
            user_id=user_id,
            current_streak=current_streak,
            longest_streak=longest_streak,
            last_activity_date=last_activity_date,
        )
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_get_streak_returns_zero_after_missed_training_day(db_session, monkeypatch) -> None:
    monkeypatch.setattr("app.services.progress_service.date", _FixedDate)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    await _seed_streak(
        db_session, user.id, current_streak=5, longest_streak=5, last_activity_date=TWO_DAYS_AGO
    )
    await _add_day_plan(db_session, user.id, day_date=YESTERDAY, session_type=DaySessionType.ON_ICE)

    result = await ProgressService(db_session).get_streak(user.id)

    assert result.current_streak == 0
    assert result.longest_streak == 5  # untouched
    assert result.last_activity_date == TWO_DAYS_AGO  # untouched

    # Not persisted -- the raw row still shows the pre-break value.
    raw = await ProgressRepository(db_session).get_streak(user.id)
    assert raw.current_streak == 5


@pytest.mark.asyncio
async def test_get_streak_keeps_value_when_gap_is_only_rest_days(db_session, monkeypatch) -> None:
    monkeypatch.setattr("app.services.progress_service.date", _FixedDate)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    await _seed_streak(
        db_session, user.id, current_streak=5, longest_streak=5, last_activity_date=TWO_DAYS_AGO
    )
    await _add_day_plan(db_session, user.id, day_date=YESTERDAY, session_type=DaySessionType.REST)

    result = await ProgressService(db_session).get_streak(user.id)

    assert result.current_streak == 5


@pytest.mark.asyncio
async def test_get_streak_keeps_value_when_last_activity_is_today(db_session, monkeypatch) -> None:
    monkeypatch.setattr("app.services.progress_service.date", _FixedDate)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    await _seed_streak(
        db_session, user.id, current_streak=3, longest_streak=3, last_activity_date=TODAY
    )

    result = await ProgressService(db_session).get_streak(user.id)

    assert result.current_streak == 3


class _FixedDate(date):
    """Patches app.services.progress_service's `date.today()` so tests don't
    depend on the wall-clock date lining up with the fixed TODAY constant
    above -- has_missed_training_day itself takes real date objects and
    doesn't need patching, only the `date.today()` call inside get_streak."""

    @classmethod
    def today(cls) -> date:
        return TODAY
