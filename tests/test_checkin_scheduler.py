"""Check-in scheduler tick: which users/restrictions get a push and
checkin_sent_at's guard against re-sending. No real push is ever sent --
webpush_async is monkeypatched at the app.services.push_service module
level, same convention as test_reminder_scheduler.py.
"""
import json
import uuid
from datetime import date, datetime, timezone

import pytest

from app.models.exercise import MovementPattern
from app.models.push_subscription import PushSubscription
from app.models.user import CoachPersonality, User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.services import push_service
from app.services.checkin_scheduler import _run_tick
from app.services.coach_personality_phrases import CHECKIN_PHRASES

MORNING_NOW = datetime(2026, 3, 10, 9, 2, tzinfo=timezone.utc)
OFF_WINDOW_NOW = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 3, 10)
YESTERDAY = date(2026, 3, 9)
TOO_OLD = date(2026, 3, 8)


def _make_user(*, timezone_name: str = "UTC", coach_personality: CoachPersonality | None = None) -> User:
    unique = uuid.uuid4().hex[:8]
    kwargs = {}
    if coach_personality is not None:
        kwargs["coach_personality"] = coach_personality
    return User(
        id=uuid.uuid4(),
        username=f"checkin_{unique}",
        email=f"checkin_{unique}@example.com",
        password_hash="irrelevant",
        timezone=timezone_name,
        **kwargs,
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


def _make_restriction(
    user_id: uuid.UUID,
    *,
    expires_at: date,
    checkin_sent_at: datetime | None = None,
    lifted_at: datetime | None = None,
) -> UserTemporaryRestriction:
    return UserTemporaryRestriction(
        id=uuid.uuid4(),
        user_id=user_id,
        movement_pattern=MovementPattern.HIP_HINGE,
        expires_at=expires_at,
        checkin_sent_at=checkin_sent_at,
        lifted_at=lifted_at,
    )


def _counting_webpush(calls: list):
    async def _fake(*args, **kwargs):
        calls.append((args, kwargs))
        return "ok"

    return _fake


@pytest.mark.asyncio
async def test_checkin_sent_for_restriction_expired_today(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(_make_subscription(user.id))
    restriction = _make_restriction(user.id, expires_at=TODAY)
    db_session.add(restriction)
    await db_session.flush()

    await _run_tick(db_session, MORNING_NOW)
    await db_session.commit()

    await db_session.refresh(restriction)
    assert restriction.checkin_sent_at is not None
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_checkin_sent_for_restriction_expired_yesterday(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(_make_subscription(user.id))
    restriction = _make_restriction(user.id, expires_at=YESTERDAY)
    db_session.add(restriction)
    await db_session.flush()

    await _run_tick(db_session, MORNING_NOW)
    await db_session.commit()

    await db_session.refresh(restriction)
    assert restriction.checkin_sent_at is not None


@pytest.mark.asyncio
async def test_restriction_expired_too_long_ago_is_not_checked_in(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(_make_subscription(user.id))
    restriction = _make_restriction(user.id, expires_at=TOO_OLD)
    db_session.add(restriction)
    await db_session.flush()

    await _run_tick(db_session, MORNING_NOW)
    await db_session.commit()

    await db_session.refresh(restriction)
    assert restriction.checkin_sent_at is None
    assert calls == []


@pytest.mark.asyncio
async def test_already_checked_in_restriction_is_not_sent_again(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(_make_subscription(user.id))
    already_sent_at = datetime(2026, 3, 10, 9, 1, tzinfo=timezone.utc)
    restriction = _make_restriction(user.id, expires_at=TODAY, checkin_sent_at=already_sent_at)
    db_session.add(restriction)
    await db_session.flush()

    await _run_tick(db_session, MORNING_NOW)
    await db_session.commit()

    await db_session.refresh(restriction)
    assert restriction.checkin_sent_at == already_sent_at
    assert calls == []


@pytest.mark.asyncio
async def test_outside_morning_window_is_not_checked_in(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(_make_subscription(user.id))
    restriction = _make_restriction(user.id, expires_at=TODAY)
    db_session.add(restriction)
    await db_session.flush()

    await _run_tick(db_session, OFF_WINDOW_NOW)
    await db_session.commit()

    await db_session.refresh(restriction)
    assert restriction.checkin_sent_at is None
    assert calls == []


@pytest.mark.asyncio
async def test_user_without_subscription_is_skipped_without_error(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    # Deliberately no PushSubscription for this user.
    restriction = _make_restriction(user.id, expires_at=TODAY)
    db_session.add(restriction)
    await db_session.flush()

    await _run_tick(db_session, MORNING_NOW)  # must not raise
    await db_session.commit()

    await db_session.refresh(restriction)
    assert restriction.checkin_sent_at is None
    assert calls == []


@pytest.mark.asyncio
async def test_checkin_body_follows_coach_personality(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))

    user = _make_user(coach_personality=CoachPersonality.HUMOR)
    db_session.add(user)
    await db_session.flush()
    db_session.add(_make_subscription(user.id))
    restriction = _make_restriction(user.id, expires_at=TODAY)
    db_session.add(restriction)
    await db_session.flush()

    await _run_tick(db_session, MORNING_NOW)
    await db_session.commit()

    assert len(calls) == 1
    body = json.loads(calls[0][1]["data"])["body"]
    assert body in CHECKIN_PHRASES[CoachPersonality.HUMOR]


@pytest.mark.asyncio
async def test_lifted_restriction_still_expired_today_still_gets_checkin(
    db_session, monkeypatch
) -> None:
    # Being lifted early doesn't opt a restriction out of the check-in --
    # checkin_sent_at is the only guard, mirroring reminder_scheduler's
    # single reminder_sent_at guard rather than adding a second condition.
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(_make_subscription(user.id))
    restriction = _make_restriction(
        user.id, expires_at=TODAY, lifted_at=datetime(2026, 3, 9, 8, 0, tzinfo=timezone.utc)
    )
    db_session.add(restriction)
    await db_session.flush()

    await _run_tick(db_session, MORNING_NOW)
    await db_session.commit()

    await db_session.refresh(restriction)
    assert restriction.checkin_sent_at is not None
    assert len(calls) == 1
