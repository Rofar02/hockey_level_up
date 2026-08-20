"""GET /users/me/activity-calendar (app.services.streak_service.
list_activity_calendar + ProgressService.get_activity_calendar) --
2026-08-19: gives the frontend calendar a real month of completion
history instead of the old fallback of "current week's WeeklyPlan plus a
single TrainingStreak.last_activity_date marker" (see HomePage.tsx's own
comment on why that stand-in existed).

fully_completed uses the same "every SessionBlock done, at least one
exists" bar as is_session_fully_completed/has_missed_training_day, so the
calendar and the streak number never disagree about which days counted --
that mismatch is exactly what caused the streak bug this same day.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.exercise import Exercise, ExerciseCategory, TrainingPhase
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.user import User
from app.routers.users import _month_bounds
from app.services.progress_service import ProgressService
from app.services.streak_service import list_activity_calendar

JAN_15 = date(2026, 1, 15)
FEB_10 = date(2026, 2, 10)
DEC_25 = date(2026, 12, 25)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"calendar_{unique}",
        email=f"calendar_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise() -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )


async def _add_day_plan(
    db_session, user_id: uuid.UUID, *, day_date: date, session_type: DaySessionType
) -> DayPlan:
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user_id, week_start_date=day_date)
    db_session.add(weekly_plan)
    await db_session.flush()
    day_plan = DayPlan(
        id=uuid.uuid4(), weekly_plan_id=weekly_plan.id, date=day_date, session_type=session_type
    )
    db_session.add(day_plan)
    await db_session.flush()
    return day_plan


async def _add_session(
    db_session, day_plan: DayPlan, exercise: Exercise, *, completed_flags: list[bool]
) -> None:
    blocks = [
        SessionBlock(
            id=uuid.uuid4(),
            phase=TrainingPhase.MAIN,
            exercise_id=exercise.id,
            order=i,
            completed_at=datetime.now(timezone.utc) if completed else None,
        )
        for i, completed in enumerate(completed_flags)
    ]
    training_session = TrainingSession(id=uuid.uuid4(), day_plan_id=day_plan.id, blocks=blocks)
    db_session.add(training_session)
    await db_session.flush()


@pytest.mark.asyncio
async def test_fully_completed_session_is_reported_as_completed(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    day_plan = await _add_day_plan(
        db_session, user.id, day_date=JAN_15, session_type=DaySessionType.OFF_ICE
    )
    await _add_session(db_session, day_plan, exercise, completed_flags=[True, True, True])

    days = await list_activity_calendar(db_session, user.id, JAN_15, JAN_15)

    assert len(days) == 1
    assert days[0].date == JAN_15
    assert days[0].session_type == DaySessionType.OFF_ICE
    assert days[0].fully_completed is True


@pytest.mark.asyncio
async def test_partially_completed_session_is_reported_as_not_completed(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    day_plan = await _add_day_plan(
        db_session, user.id, day_date=JAN_15, session_type=DaySessionType.OFF_ICE
    )
    # Only warmup done, MAIN/cooldown still pending -- the exact real-world
    # shape that inflated a streak to 6 the same day this endpoint was built.
    await _add_session(db_session, day_plan, exercise, completed_flags=[True, False, False])

    days = await list_activity_calendar(db_session, user.id, JAN_15, JAN_15)

    assert days[0].fully_completed is False


@pytest.mark.asyncio
async def test_rest_day_has_no_blocks_and_is_not_completed(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    await _add_day_plan(db_session, user.id, day_date=JAN_15, session_type=DaySessionType.REST)

    days = await list_activity_calendar(db_session, user.id, JAN_15, JAN_15)

    assert len(days) == 1
    assert days[0].session_type == DaySessionType.REST
    assert days[0].fully_completed is False


@pytest.mark.asyncio
async def test_days_outside_the_range_are_excluded(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    await _add_day_plan(
        db_session, user.id, day_date=JAN_15 - timedelta(days=1), session_type=DaySessionType.REST
    )
    await _add_day_plan(db_session, user.id, day_date=JAN_15, session_type=DaySessionType.REST)
    await _add_day_plan(
        db_session, user.id, day_date=JAN_15 + timedelta(days=1), session_type=DaySessionType.REST
    )

    days = await list_activity_calendar(db_session, user.id, JAN_15, JAN_15)

    assert [d.date for d in days] == [JAN_15]


@pytest.mark.asyncio
async def test_other_users_day_plans_are_not_included(db_session) -> None:
    user = _make_user()
    other_user = _make_user()
    db_session.add_all([user, other_user])
    await db_session.flush()
    await _add_day_plan(
        db_session, other_user.id, day_date=JAN_15, session_type=DaySessionType.OFF_ICE
    )

    days = await list_activity_calendar(db_session, user.id, JAN_15, JAN_15)

    assert days == []


@pytest.mark.asyncio
async def test_date_with_no_day_plan_at_all_is_simply_absent(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    days = await list_activity_calendar(db_session, user.id, JAN_15, JAN_15)

    assert days == []


@pytest.mark.asyncio
async def test_progress_service_shapes_the_response_for_a_multi_day_range(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    day1 = await _add_day_plan(
        db_session, user.id, day_date=JAN_15, session_type=DaySessionType.OFF_ICE
    )
    await _add_session(db_session, day1, exercise, completed_flags=[True])
    day2 = await _add_day_plan(
        db_session, user.id, day_date=JAN_15 + timedelta(days=1), session_type=DaySessionType.OFF_ICE
    )
    await _add_session(db_session, day2, exercise, completed_flags=[False])

    result = await ProgressService(db_session).get_activity_calendar(
        user.id, from_date=JAN_15, to_date=JAN_15 + timedelta(days=1)
    )

    assert [(r.date, r.fully_completed) for r in result] == [
        (JAN_15, True),
        (JAN_15 + timedelta(days=1), False),
    ]


@pytest.mark.parametrize(
    ("month", "expected_from", "expected_to"),
    [
        (FEB_10, date(2026, 2, 1), date(2026, 2, 28)),  # 2026 isn't a leap year
        (DEC_25, date(2026, 12, 1), date(2026, 12, 31)),  # December -> January wraparound
    ],
)
def test_month_bounds(month: date, expected_from: date, expected_to: date) -> None:
    assert _month_bounds(month) == (expected_from, expected_to)
