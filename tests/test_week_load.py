"""Release plan step 5 (2026-10-09): light legs on the gym day after ice or
a game (5.1), and the shadow-only reaction to real leg overload (5.2).
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.week_load import is_overloaded, light_legs_dates
from app.models.progress import IceLoadCharge
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.user import User
from app.schemas.schedule import DayPlanIn, WeeklyPlanCreate
from app.services.schedule_service import ScheduleService
from app.services.week_load_service import evaluate_week_after_ice

MONDAY = date(2026, 3, 9)
ICE, GYM, REST, GAME = DaySessionType.ON_ICE, DaySessionType.OFF_ICE, DaySessionType.REST, DaySessionType.GAME


def _week(*kinds: DaySessionType) -> list[tuple[date, DaySessionType]]:
    return [(MONDAY + timedelta(days=i), kind) for i, kind in enumerate(kinds)]


def test_gym_after_ice_or_game_is_light_when_another_gym_day_exists() -> None:
    week = _week(ICE, GYM, REST, GYM, GAME, GYM, REST)
    assert light_legs_dates(week) == {MONDAY + timedelta(days=1), MONDAY + timedelta(days=5)}


def test_legs_stay_at_least_once_a_week() -> None:
    week = _week(ICE, GYM, ICE, GYM, REST, REST, REST)
    assert light_legs_dates(week) == {MONDAY + timedelta(days=3)}


def test_no_ice_no_light_days() -> None:
    assert light_legs_dates(_week(GYM, REST, GYM, REST, GYM, REST, REST)) == set()


def test_overload_is_relative_to_the_players_habit() -> None:
    assert is_overloaded(acute=9.0, habitual=4.0)
    assert not is_overloaded(acute=9.0, habitual=7.0)  # skates a lot anyway
    assert not is_overloaded(acute=4.0, habitual=0.0)  # below the absolute floor


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(id=uuid.uuid4(), username=f"wl_{unique}", email=f"wl_{unique}@example.com", password_hash="x")


@pytest.mark.asyncio
async def test_create_weekly_plan_builds_light_legs_day_after_ice(db_session, monkeypatch) -> None:
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "week_light_legs_after_ice", True)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    seen: dict[date, bool] = {}

    async def fake_build(self, session_type, user, block_phase, training_block=None, *, today=None, light_legs=False, **_):
        seen[today] = light_legs
        return TrainingSession(blocks=[])

    monkeypatch.setattr(ScheduleService, "_build_session_for_day", fake_build)
    days = [DayPlanIn(date=d, session_type=kind) for d, kind in _week(ICE, GYM, REST, GYM, REST, REST, REST)]
    await ScheduleService(db_session).create_weekly_plan(user, WeeklyPlanCreate(days=days))

    assert seen[MONDAY + timedelta(days=1)] is True
    assert seen[MONDAY + timedelta(days=3)] is False


@pytest.mark.asyncio
async def test_light_legs_switch_off(db_session, monkeypatch) -> None:
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "week_light_legs_after_ice", False)
    assert ScheduleService._light_legs_dates_for(None, _week(ICE, GYM, REST, GYM, REST, REST, REST)) == set()


@pytest.mark.asyncio
async def test_shadow_evaluation_needs_overload_and_a_heavy_day(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    # Two heavy ice charges in the last 48 h, nothing before: acute way over habit.
    for _ in range(2):
        session = TrainingSession(id=uuid.uuid4(), blocks=[])
        day = DayPlan(id=uuid.uuid4(), date=now.date(), session_type=ICE, training_session=session)
        db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=now.date() - timedelta(days=_), day_plans=[day]))
        await db_session.flush()
        db_session.add(IceLoadCharge(training_session_id=session.id, user_id=user.id, scale=1.5))
    await db_session.flush()

    # Overloaded, but no gym day with heavy legs ahead -> nothing to do.
    assert await evaluate_week_after_ice(db_session, user.id, now) is None


@pytest.mark.asyncio
async def test_shadow_evaluation_flags_heavy_leg_day_after_overload(db_session) -> None:
    from app.models.exercise import Exercise, ExerciseCategory, ExerciseMuscleGroup, MuscleGroup, TrainingPhase
    from app.models.schedule import SessionBlock

    user = _make_user()
    db_session.add(user)
    squat = Exercise(
        id=uuid.uuid4(), name=f"wl squat {uuid.uuid4().hex[:6]}", category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN, difficulty_level=5,
    )
    db_session.add(squat)
    await db_session.flush()
    db_session.add(ExerciseMuscleGroup(exercise_id=squat.id, muscle_group=MuscleGroup.GLUTES, weight=1.0))
    now = datetime.now(timezone.utc)

    ice = TrainingSession(id=uuid.uuid4(), blocks=[])
    gym = TrainingSession(id=uuid.uuid4(), blocks=[SessionBlock(exercise_id=squat.id, phase=TrainingPhase.MAIN, order=0)])
    days = [
        DayPlan(id=uuid.uuid4(), date=now.date(), session_type=ICE, training_session=ice),
        DayPlan(id=uuid.uuid4(), date=now.date() + timedelta(days=1), session_type=GYM, training_session=gym),
    ]
    db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=now.date(), day_plans=days))
    await db_session.flush()
    db_session.add(IceLoadCharge(training_session_id=ice.id, user_id=user.id, scale=1.5))
    await db_session.flush()

    decision = await evaluate_week_after_ice(db_session, user.id, now)

    assert decision is not None
    assert decision["day"] == (now.date() + timedelta(days=1)).isoformat()
    assert "glutes" in decision["overloaded"]
