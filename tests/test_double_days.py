"""Double days (2026-10-09, release plan step 6): a separate full gym
training on an ice or game day, morning or evening, behind
settings.double_days_enabled.
"""
import uuid
from datetime import date, timedelta

import pytest

from app.core import config
from app.models.schedule import DaySessionType, TrainingSession
from app.models.user import User
from app.schemas.schedule import DayPlanIn, WeeklyPlanCreate, WeeklyPlanPatch
from app.services.schedule_service import ScheduleService

MONDAY = date(2030, 3, 4)
ICE, GYM, REST, GAME = DaySessionType.ON_ICE, DaySessionType.OFF_ICE, DaySessionType.REST, DaySessionType.GAME


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(id=uuid.uuid4(), username=f"dd_{unique}", email=f"dd_{unique}@example.com", password_hash="x", timezone="UTC")


@pytest.fixture
def builds(monkeypatch):
    """Records each built session's (date, type, light_legs) -- no catalog needed."""
    seen: list[tuple[date, DaySessionType, bool]] = []

    async def fake_build(self, session_type, user, block_phase, training_block=None, *, today=None, light_legs=False, **_):
        seen.append((today, session_type, light_legs))
        return TrainingSession(blocks=[])

    monkeypatch.setattr(ScheduleService, "_build_session_for_day", fake_build)
    return seen


def _days(extra_on: dict[int, str]) -> list[DayPlanIn]:
    kinds = [ICE, GYM, GAME, REST, REST, GYM, REST]
    return [
        DayPlanIn(date=MONDAY + timedelta(days=i), session_type=kind, extra_gym=extra_on.get(i))
        for i, kind in enumerate(kinds)
    ]


@pytest.mark.asyncio
async def test_switch_off_ignores_extra_gym(db_session, builds, monkeypatch) -> None:
    monkeypatch.setattr(config.get_settings(), "double_days_enabled", False)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    plan = await ScheduleService(db_session).create_weekly_plan(user, WeeklyPlanCreate(days=_days({0: "morning"})))

    assert len(plan.day_plans) == 7
    assert not any(d.is_extra for d in plan.day_plans)


@pytest.mark.asyncio
async def test_extra_gym_day_next_to_ice_and_game(db_session, builds, monkeypatch) -> None:
    monkeypatch.setattr(config.get_settings(), "double_days_enabled", True)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    plan = await ScheduleService(db_session).create_weekly_plan(
        user, WeeklyPlanCreate(days=_days({0: "morning", 2: "evening", 1: "morning"}))
    )

    extras = sorted((d for d in plan.day_plans if d.is_extra), key=lambda d: d.date)
    assert [(d.date, d.session_type, d.time_of_day) for d in extras] == [
        (MONDAY, GYM, "morning"),
        (MONDAY + timedelta(days=2), GYM, "evening"),
    ]
    mains = {d.date: d for d in plan.day_plans if not d.is_extra}
    assert mains[MONDAY].time_of_day == "evening"
    assert mains[MONDAY + timedelta(days=2)].time_of_day == "morning"
    # The double day's gym is an ordinary gym day -- full legs.
    assert (MONDAY, GYM, False) in builds
    assert not any(light for _, _, light in builds)


@pytest.mark.asyncio
async def test_patch_removes_and_moves_the_extra_day(db_session, builds, monkeypatch) -> None:
    monkeypatch.setattr(config.get_settings(), "double_days_enabled", True)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    service = ScheduleService(db_session)
    await service.create_weekly_plan(user, WeeklyPlanCreate(days=_days({0: "morning", 2: "evening"})))

    result = await service.patch_weekly_plan(
        user,
        WeeklyPlanPatch(
            days=[
                DayPlanIn(date=MONDAY, session_type=ICE, extra_gym="evening"),
                DayPlanIn(date=MONDAY + timedelta(days=2), session_type=REST),
            ]
        ),
        MONDAY,
    )

    extras = [d for d in result.weekly_plan.day_plans if d.is_extra]
    assert [(d.date, d.time_of_day) for d in extras] == [(MONDAY, "evening")]


@pytest.mark.asyncio
async def test_day_lookup_by_date_returns_the_main_day(db_session, builds, monkeypatch) -> None:
    monkeypatch.setattr(config.get_settings(), "double_days_enabled", True)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    service = ScheduleService(db_session)
    await service.create_weekly_plan(user, WeeklyPlanCreate(days=_days({0: "morning"})))

    day = await service.get_day_plan_for_date(user, MONDAY)

    assert day.session_type == ICE and day.is_extra is False


@pytest.mark.asyncio
async def test_adding_the_extra_gym_leaves_the_day_itself_alone(db_session, builds, monkeypatch) -> None:
    """Only "+ зал" changed: the ice day keeps its session and its team
    event link (2026-10-10, found on the demo -- it used to be rebuilt and
    unlinked from the team training)."""
    monkeypatch.setattr(config.get_settings(), "double_days_enabled", True)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    service = ScheduleService(db_session)
    plan = await service.create_weekly_plan(user, WeeklyPlanCreate(days=_days({})))
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.schedule import DayPlan

    def main_day():
        return (
            select(DayPlan)
            .where(DayPlan.weekly_plan_id == plan.id, DayPlan.date == MONDAY, DayPlan.is_extra.is_(False))
            .options(selectinload(DayPlan.training_session))
            .execution_options(populate_existing=True)
        )

    monday = await db_session.scalar(main_day())
    session_before = monday.training_session.id
    from datetime import datetime, time, timezone

    from app.models.team_event import TeamEventType
    from app.services.team_event_service import TeamEventService
    from app.services.team_service import TeamService

    team = await TeamService(db_session).create_team(user, "Двойные")
    event = await TeamEventService(db_session).create_event(
        user, team.id, TeamEventType.TRAINING, datetime.combine(MONDAY, time(19), tzinfo=timezone.utc), None
    )
    team_event_id = event.id
    monday.team_event_id = team_event_id
    await db_session.flush()

    result = await service.patch_weekly_plan(
        user, WeeklyPlanPatch(days=[DayPlanIn(date=MONDAY, session_type=ICE, extra_gym="evening")]), MONDAY
    )

    assert result.conflicts == []
    monday = await db_session.scalar(main_day())
    assert monday.training_session.id == session_before
    assert monday.team_event_id == team_event_id
    extras = [d for d in result.weekly_plan.day_plans if d.is_extra]
    assert [(d.date, d.time_of_day) for d in extras] == [(MONDAY, "evening")]
