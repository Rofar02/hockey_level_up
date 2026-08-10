"""Reminder scheduler tick: which users/day-plans get a push and
reminder_sent_at's guard against re-sending. No real push is ever sent --
webpush_async is monkeypatched at the app.services.push_service module
level, same convention as test_push_subscription.py.
"""
import json
import uuid
from datetime import date, datetime, timezone

import pytest

from app.models.push_subscription import PushSubscription
from app.models.schedule import DayPlan, DaySessionType, WeeklyPlan
from app.models.user import ReminderPreference, User
from app.services import push_service
from app.services.reminder_scheduler import _run_tick

MORNING_NOW = datetime(2026, 3, 10, 9, 2, tzinfo=timezone.utc)
EVENING_NOW = datetime(2026, 3, 10, 19, 2, tzinfo=timezone.utc)
WEEK_START = date(2026, 3, 9)
TODAY = date(2026, 3, 10)
TOMORROW = date(2026, 3, 11)


def _make_user(*, reminder_preference: ReminderPreference, timezone_name: str = "UTC") -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"reminder_{unique}",
        email=f"reminder_{unique}@example.com",
        password_hash="irrelevant",
        reminder_preference=reminder_preference,
        timezone=timezone_name,
    )


def _make_subscription(user_id: uuid.UUID) -> PushSubscription:
    return PushSubscription(
        id=uuid.uuid4(),
        user_id=user_id,
        endpoint=f"https://push.example.com/{uuid.uuid4().hex}",
        p256dh_key="p256dh-test-key",
        auth_key="auth-test-key",
        user_agent="pytest",
    )


async def _make_weekly_plan(db_session, user_id: uuid.UUID) -> WeeklyPlan:
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user_id, week_start_date=WEEK_START)
    db_session.add(weekly_plan)
    await db_session.flush()
    return weekly_plan


async def _add_day_plan(
    db_session,
    weekly_plan_id: uuid.UUID,
    *,
    day_date: date,
    session_type: DaySessionType,
    reminder_sent_at: datetime | None = None,
) -> DayPlan:
    day_plan = DayPlan(
        id=uuid.uuid4(),
        weekly_plan_id=weekly_plan_id,
        date=day_date,
        session_type=session_type,
        reminder_sent_at=reminder_sent_at,
    )
    db_session.add(day_plan)
    await db_session.flush()
    return day_plan


async def _fake_webpush_success(*_args, **_kwargs) -> str:
    return "ok"


def _counting_webpush(calls: list):
    async def _fake(*args, **kwargs):
        calls.append((args, kwargs))
        return "ok"

    return _fake


@pytest.mark.asyncio
async def test_morning_reminder_targets_today(db_session, monkeypatch) -> None:
    monkeypatch.setattr(push_service, "webpush_async", _fake_webpush_success)

    user = _make_user(reminder_preference=ReminderPreference.MORNING)
    db_session.add(user)
    await db_session.flush()
    db_session.add(_make_subscription(user.id))
    await db_session.flush()
    weekly_plan = await _make_weekly_plan(db_session, user.id)
    today_plan = await _add_day_plan(
        db_session, weekly_plan.id, day_date=TODAY, session_type=DaySessionType.ON_ICE
    )
    tomorrow_plan = await _add_day_plan(
        db_session, weekly_plan.id, day_date=TOMORROW, session_type=DaySessionType.ON_ICE
    )

    await _run_tick(db_session, MORNING_NOW)
    # _run_tick relies on the production wrapper's session.begin() to
    # commit -- called bare here, we commit ourselves so the refresh()
    # below (which doesn't autoflush) sees the write instead of stale data.
    await db_session.commit()

    await db_session.refresh(today_plan)
    await db_session.refresh(tomorrow_plan)
    assert today_plan.reminder_sent_at is not None
    assert tomorrow_plan.reminder_sent_at is None


@pytest.mark.asyncio
async def test_game_day_reminder_does_not_crash_and_uses_game_wording(db_session, monkeypatch) -> None:
    # _SESSION_TYPE_TEXT only has ON_ICE/OFF_ICE entries -- a GAME day (also
    # not REST, so _due_day_plan picks it up) must not KeyError there.
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))

    user = _make_user(reminder_preference=ReminderPreference.MORNING)
    db_session.add(user)
    await db_session.flush()
    db_session.add(_make_subscription(user.id))
    await db_session.flush()
    weekly_plan = await _make_weekly_plan(db_session, user.id)
    today_plan = await _add_day_plan(
        db_session, weekly_plan.id, day_date=TODAY, session_type=DaySessionType.GAME
    )

    await _run_tick(db_session, MORNING_NOW)  # must not raise
    await db_session.commit()

    await db_session.refresh(today_plan)
    assert today_plan.reminder_sent_at is not None
    assert len(calls) == 1
    body = json.loads(calls[0][1]["data"])["body"]
    assert "игра" in body.lower()


@pytest.mark.asyncio
async def test_evening_reminder_targets_tomorrow(db_session, monkeypatch) -> None:
    monkeypatch.setattr(push_service, "webpush_async", _fake_webpush_success)

    user = _make_user(reminder_preference=ReminderPreference.EVENING)
    db_session.add(user)
    await db_session.flush()
    db_session.add(_make_subscription(user.id))
    await db_session.flush()
    weekly_plan = await _make_weekly_plan(db_session, user.id)
    today_plan = await _add_day_plan(
        db_session, weekly_plan.id, day_date=TODAY, session_type=DaySessionType.ON_ICE
    )
    tomorrow_plan = await _add_day_plan(
        db_session, weekly_plan.id, day_date=TOMORROW, session_type=DaySessionType.OFF_ICE
    )

    await _run_tick(db_session, EVENING_NOW)
    await db_session.commit()

    await db_session.refresh(today_plan)
    await db_session.refresh(tomorrow_plan)
    assert today_plan.reminder_sent_at is None
    assert tomorrow_plan.reminder_sent_at is not None


@pytest.mark.asyncio
async def test_rest_day_is_not_reminded(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))

    user = _make_user(reminder_preference=ReminderPreference.MORNING)
    db_session.add(user)
    await db_session.flush()
    db_session.add(_make_subscription(user.id))
    await db_session.flush()
    weekly_plan = await _make_weekly_plan(db_session, user.id)
    rest_plan = await _add_day_plan(
        db_session, weekly_plan.id, day_date=TODAY, session_type=DaySessionType.REST
    )

    await _run_tick(db_session, MORNING_NOW)
    await db_session.commit()

    await db_session.refresh(rest_plan)
    assert rest_plan.reminder_sent_at is None
    assert calls == []


@pytest.mark.asyncio
async def test_already_sent_reminder_is_not_sent_again(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))

    user = _make_user(reminder_preference=ReminderPreference.MORNING)
    db_session.add(user)
    await db_session.flush()
    db_session.add(_make_subscription(user.id))
    await db_session.flush()
    weekly_plan = await _make_weekly_plan(db_session, user.id)
    already_sent_at = datetime(2026, 3, 10, 9, 1, tzinfo=timezone.utc)
    day_plan = await _add_day_plan(
        db_session,
        weekly_plan.id,
        day_date=TODAY,
        session_type=DaySessionType.ON_ICE,
        reminder_sent_at=already_sent_at,
    )

    await _run_tick(db_session, MORNING_NOW)
    await db_session.commit()

    await db_session.refresh(day_plan)
    assert day_plan.reminder_sent_at == already_sent_at
    assert calls == []


@pytest.mark.asyncio
async def test_user_without_subscriptions_is_skipped_without_error(
    db_session, monkeypatch
) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))

    user = _make_user(reminder_preference=ReminderPreference.MORNING)
    db_session.add(user)
    await db_session.flush()
    # Deliberately no PushSubscription for this user.
    weekly_plan = await _make_weekly_plan(db_session, user.id)
    day_plan = await _add_day_plan(
        db_session, weekly_plan.id, day_date=TODAY, session_type=DaySessionType.ON_ICE
    )

    await _run_tick(db_session, MORNING_NOW)  # must not raise
    await db_session.commit()

    await db_session.refresh(day_plan)
    assert day_plan.reminder_sent_at is None
    assert calls == []
