"""Instant pushes fired straight from TeamEventService: game scheduled,
board/lineup published (once, not on a repeat publish), reschedule,
cancel. webpush_async is monkeypatched at the app.services.push_service
module level, same convention as test_reminder_scheduler.py.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.push_subscription import PushSubscription
from app.models.team_event import TeamEventType
from app.models.user import User
from app.services import push_service
from app.services.team_event_service import TeamEventService
from app.services.team_service import TeamService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"notif_{unique}",
        email=f"notif_{unique}@example.com",
        password_hash="irrelevant",
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


def _future(hours: int = 48) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


async def _make_team_with_player(db_session):
    captain = _make_user()
    player = _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()
    db_session.add_all([_make_subscription(captain.id), _make_subscription(player.id)])
    await db_session.flush()

    teams = TeamService(db_session)
    team = await teams.create_team(captain, "Sharks")
    request = await teams.join_by_code(player, team.invite_code)
    await teams.approve_request(captain, request.id)
    return captain, player, team


@pytest.mark.asyncio
async def test_game_scheduled_pushes_team_training_does_not(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    await events.create_event(captain, team.id, TeamEventType.GAME, _future(), "Rival HC")
    assert len(calls) == 2  # captain + player, one subscription each

    calls.clear()
    await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    assert calls == []


@pytest.mark.asyncio
async def test_publish_board_pushes_once_not_on_repeat(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)

    await events.publish_board(captain, team.id, event.id)
    assert len(calls) == 2

    calls.clear()
    await events.publish_board(captain, team.id, event.id)
    assert calls == []


@pytest.mark.asyncio
async def test_publish_lineup_pushes_once_not_on_repeat(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)

    await events.publish_lineup(captain, team.id, event.id)
    assert len(calls) == 2

    calls.clear()
    await events.publish_lineup(captain, team.id, event.id)
    assert calls == []


@pytest.mark.asyncio
async def test_reschedule_pushes_team_and_requires_captain(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    calls.clear()

    new_time = _future(72)
    updated = await events.reschedule_event(captain, team.id, event.id, new_time)
    assert updated.starts_at == new_time
    assert len(calls) == 2

    with pytest.raises(HTTPException) as exc_info:
        await events.reschedule_event(player, team.id, event.id, _future(96))
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_cancel_pushes_team_and_blocks_second_cancel(db_session, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(push_service, "webpush_async", _counting_webpush(calls))
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    calls.clear()

    cancelled = await events.cancel_event(captain, team.id, event.id)
    assert cancelled.status == "cancelled"
    assert len(calls) == 2

    with pytest.raises(HTTPException) as exc_info:
        await events.cancel_event(captain, team.id, event.id)
    assert exc_info.value.status_code == 409

    with pytest.raises(HTTPException) as exc_info:
        await events.reschedule_event(captain, team.id, event.id, _future(96))
    assert exc_info.value.status_code == 409
