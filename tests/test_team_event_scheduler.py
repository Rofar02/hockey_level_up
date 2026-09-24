"""team_event_scheduler tick: attendance summary at the -2h deadline, and
the morning "board not ready" push. No real push is ever sent --
webpush_async is monkeypatched, same convention as test_reminder_scheduler.py.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.push_subscription import PushSubscription
from app.models.team_event import TeamEventAttendanceStatus, TeamEventType
from app.models.user import User
from app.services import push_service
from app.services.team_event_scheduler import _run_tick
from app.services.team_event_service import TeamEventService
from app.services.team_service import TeamService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"sched_{unique}",
        email=f"sched_{unique}@example.com",
        password_hash="irrelevant",
        timezone="UTC",
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_subscription(user_id: uuid.UUID) -> PushSubscription:
    return PushSubscription(
        id=uuid.uuid4(),
        user_id=user_id,
        endpoint=f"https://push.example.com/{uuid.uuid4().hex}",
        p256dh_key="p256dh-test-key",
        auth_key="auth-test-key",
        user_agent="pytest",
    )


def _counting_webpush(calls: list):
    async def _fake(*args, **kwargs):
        calls.append((args, kwargs))
        return "ok"

    return _fake


async def _make_team_with_player(db_session):
    captain = _make_user()
    player = _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()
    db_session.add(_make_subscription(captain.id))
    await db_session.flush()

    teams = TeamService(db_session)
    team = await teams.create_team(captain, "Sharks")
    request = await teams.join_by_code(player, team.invite_code)
    await teams.approve_request(captain, request.id)
    return captain, player, team


@pytest.mark.asyncio
async def test_attendance_summary_sent_once_at_deadline(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    now = datetime.now(timezone.utc)
    # Created far out so attendance is still open to mark, then moved to
    # inside the -2h window -- reschedule_event isn't itself lock-guarded.
    event = await events.create_event(
        captain, team.id, TeamEventType.TRAINING, now + timedelta(hours=10), None
    )
    await events.set_my_attendance(
        player, team.id, event.id, TeamEventAttendanceStatus.GOING, None, None
    )
    await events.reschedule_event(captain, team.id, event.id, now + timedelta(hours=1, minutes=30))
    calls.clear()  # discard the reschedule push itself

    await _run_tick(db_session, now)
    assert len(calls) == 1  # captain only

    calls.clear()
    await _run_tick(db_session, now + timedelta(minutes=5))
    assert calls == []  # guarded by attendance_summary_sent_at


@pytest.mark.asyncio
async def test_attendance_summary_not_due_before_deadline(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    now = datetime.now(timezone.utc)
    starts_at = now + timedelta(hours=5)  # well outside the -2h window
    await events.create_event(captain, team.id, TeamEventType.TRAINING, starts_at, None)

    await _run_tick(db_session, now)
    assert calls == []


@pytest.mark.asyncio
async def test_board_not_ready_sent_in_morning_window_for_draft_training(
    db_session, monkeypatch
) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    morning = datetime(2026, 3, 10, 9, 2, tzinfo=timezone.utc)
    starts_at = datetime(2026, 3, 10, 18, 0, tzinfo=timezone.utc)  # same UTC day, evening
    await events.create_event(captain, team.id, TeamEventType.TRAINING, starts_at, None)

    await _run_tick(db_session, morning)
    assert len(calls) == 1  # captain only, board still draft

    calls.clear()
    await _run_tick(db_session, morning + timedelta(minutes=5))
    assert calls == []  # guarded by board_not_ready_sent_at


@pytest.mark.asyncio
async def test_board_not_ready_skipped_once_published(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    morning = datetime(2026, 3, 10, 9, 2, tzinfo=timezone.utc)
    starts_at = datetime(2026, 3, 10, 18, 0, tzinfo=timezone.utc)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, starts_at, None)
    await events.publish_board(captain, team.id, event.id)
    calls.clear()  # discard the publish push itself

    await _run_tick(db_session, morning)
    assert calls == []


@pytest.mark.asyncio
async def test_board_not_ready_skipped_outside_morning_window(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    afternoon = datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc)
    starts_at = datetime(2026, 3, 10, 18, 0, tzinfo=timezone.utc)
    await events.create_event(captain, team.id, TeamEventType.TRAINING, starts_at, None)

    await _run_tick(db_session, afternoon)
    assert calls == []
