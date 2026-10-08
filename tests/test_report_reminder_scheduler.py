"""Report reminder tick (2026-10-08): "how did the ice/game go?" a couple of
hours after an ON_ICE/GAME day -- when it fires for an own day and for a team
event, that a diary entry or the opt-out silences it, that a long-late one is
dropped, and report_reminder_sent_at's guard against re-sending. No real push
is sent -- webpush_async is monkeypatched, same as test_reminder_scheduler.py.
"""
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.push_subscription import PushSubscription
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.team_event import TeamEvent, TeamEventType
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import ReminderPreference, User
from app.services import push_service
from app.services.report_reminder_scheduler import _run_tick
from app.services.team_service import TeamService

WEEK_START = date(2026, 3, 9)
TODAY = date(2026, 3, 10)
YESTERDAY = date(2026, 3, 9)


def _at(hour: int, minute: int = 0, day: date = TODAY) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


async def _user(db_session, preference: ReminderPreference = ReminderPreference.EVENING) -> User:
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"report_{unique}",
        email=f"report_{unique}@example.com",
        password_hash="irrelevant",
        reminder_preference=preference,
        timezone="UTC",
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        PushSubscription(
            id=uuid.uuid4(),
            user_id=user.id,
            endpoint=f"https://push.example.com/{uuid.uuid4().hex}",
            p256dh_key="p256dh-test-key",
            auth_key="auth-test-key",
            user_agent="pytest",
        )
    )
    await db_session.flush()
    return user


async def _day(
    db_session,
    user: User,
    session_type: DaySessionType = DaySessionType.ON_ICE,
    *,
    day: date = TODAY,
    team_event_id: uuid.UUID | None = None,
) -> DayPlan:
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=WEEK_START)
    day_plan = DayPlan(
        id=uuid.uuid4(),
        date=day,
        session_type=session_type,
        team_event_id=team_event_id,
        training_session=TrainingSession(id=uuid.uuid4(), blocks=[]),
    )
    weekly_plan.day_plans.append(day_plan)
    db_session.add(weekly_plan)
    await db_session.flush()
    return day_plan


def _capture(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def _fake(*_args, **kwargs):
        sent.append(json.loads(kwargs["data"]))
        return "ok"

    monkeypatch.setattr(push_service, "webpush_async", _fake)
    return sent


async def _tick(db_session, now: datetime) -> None:
    await _run_tick(db_session, now)
    await db_session.commit()


@pytest.mark.asyncio
async def test_own_ice_day_is_asked_in_the_evening_once(db_session, monkeypatch) -> None:
    sent = _capture(monkeypatch)
    user = await _user(db_session)
    day_plan = await _day(db_session, user)

    await _tick(db_session, _at(20, 50))
    assert sent == []

    await _tick(db_session, _at(21, 2))
    await _tick(db_session, _at(21, 7))
    assert len(sent) == 1
    assert sent[0]["title"] == "Как прошёл лёд?"
    assert sent[0]["url"] == f"/training/{day_plan.id}/diary"
    await db_session.refresh(day_plan)
    assert day_plan.report_reminder_sent_at is not None


@pytest.mark.asyncio
async def test_team_game_is_asked_two_hours_after_it_ends(db_session, monkeypatch) -> None:
    sent = _capture(monkeypatch)
    user = await _user(db_session)
    team = await TeamService(db_session).create_team(user, "Sharks")
    event = TeamEvent(id=uuid.uuid4(), team_id=team.id, event_type=TeamEventType.GAME, starts_at=_at(12))
    db_session.add(event)
    await db_session.flush()
    await _day(db_session, user, DaySessionType.GAME, team_event_id=event.id)

    await _tick(db_session, _at(15, 55))  # game 12:00-14:00, asked from 16:00
    assert sent == []
    await _tick(db_session, _at(16, 2))
    assert [push["title"] for push in sent] == ["Как сыграли?"]


@pytest.mark.asyncio
async def test_no_reminder_once_the_diary_has_an_entry(db_session, monkeypatch) -> None:
    sent = _capture(monkeypatch)
    user = await _user(db_session)
    day_plan = await _day(db_session, user)
    db_session.add(
        TrainingDiaryEntry(user_id=user.id, training_session_id=day_plan.training_session.id, note=None)
    )
    await db_session.flush()

    await _tick(db_session, _at(21, 2))

    assert sent == []


@pytest.mark.asyncio
async def test_off_ice_days_and_opted_out_players_get_nothing(db_session, monkeypatch) -> None:
    sent = _capture(monkeypatch)
    user = await _user(db_session)
    await _day(db_session, user, DaySessionType.OFF_ICE)
    opted_out = await _user(db_session, ReminderPreference.NONE)
    await _day(db_session, opted_out)

    await _tick(db_session, _at(21, 2))

    assert sent == []


@pytest.mark.asyncio
async def test_a_long_late_reminder_is_dropped(db_session, monkeypatch) -> None:
    sent = _capture(monkeypatch)
    user = await _user(db_session)
    await _day(db_session, user, day=YESTERDAY)

    # Due yesterday 21:00; the worker comes back 13 hours later.
    await _tick(db_session, _at(21, 0, YESTERDAY) + timedelta(hours=13))

    assert sent == []
