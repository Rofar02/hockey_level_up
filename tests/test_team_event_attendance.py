"""TeamEventService attendance slice: going/not_going/unmarked, the -2h
freeze, the roster breakdown, and the captain's rate-limited nudge push.
webpush_async is monkeypatched at the app.services.push_service module
level, same convention as test_reminder_scheduler.py.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.push_subscription import PushSubscription
from app.models.team_event import TeamEventAbsenceReason, TeamEventAttendanceStatus, TeamEventType
from app.models.user import User
from app.services import push_service
from app.services.team_event_service import TeamEventService
from app.services.team_service import TeamService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"attendance_{unique}",
        email=f"attendance_{unique}@example.com",
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


async def _fake_webpush_success(*_args, **_kwargs) -> str:
    return "ok"


async def _make_team_with_player(db_session):
    captain = _make_user()
    player = _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()

    teams = TeamService(db_session)
    team = await teams.create_team(captain, "Sharks")
    request = await teams.join_by_code(player, team.invite_code)
    await teams.approve_request(captain, request.id)
    return captain, player, team


@pytest.mark.asyncio
async def test_going_rejects_reason_not_going_requires_it(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    starts_at = datetime.now(timezone.utc) + timedelta(hours=48)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, starts_at, None)

    with pytest.raises(HTTPException) as exc_info:
        await events.set_my_attendance(
            player, team.id, event.id, TeamEventAttendanceStatus.NOT_GOING, None, None
        )
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        await events.set_my_attendance(
            player,
            team.id,
            event.id,
            TeamEventAttendanceStatus.GOING,
            TeamEventAbsenceReason.WORK,
            None,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_roster_buckets_going_not_going_unmarked(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    starts_at = datetime.now(timezone.utc) + timedelta(hours=48)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, starts_at, None)

    await events.set_my_attendance(
        captain, team.id, event.id, TeamEventAttendanceStatus.GOING, None, None
    )
    await events.set_my_attendance(
        player,
        team.id,
        event.id,
        TeamEventAttendanceStatus.NOT_GOING,
        TeamEventAbsenceReason.INJURY,
        "twisted ankle",
    )

    roster = await events.get_attendance_roster(captain, team.id, event.id)
    assert [m.user_id for m in roster.going] == [captain.id]
    assert [m.user_id for m in roster.not_going] == [player.id]
    assert roster.not_going[0].reason == TeamEventAbsenceReason.INJURY
    assert roster.unmarked == []
    assert roster.is_locked is False


@pytest.mark.asyncio
async def test_clear_attendance_returns_to_unmarked(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    starts_at = datetime.now(timezone.utc) + timedelta(hours=48)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, starts_at, None)

    await events.set_my_attendance(
        player, team.id, event.id, TeamEventAttendanceStatus.GOING, None, None
    )
    await events.clear_my_attendance(player, team.id, event.id)

    roster = await events.get_attendance_roster(captain, team.id, event.id)
    assert roster.going == []
    assert {m.user_id for m in roster.unmarked} == {captain.id, player.id}


@pytest.mark.asyncio
async def test_attendance_locked_past_deadline(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    # 1h out -- inside the -2h deadline window, already frozen.
    starts_at = datetime.now(timezone.utc) + timedelta(hours=1)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, starts_at, None)

    with pytest.raises(HTTPException) as exc_info:
        await events.set_my_attendance(
            player, team.id, event.id, TeamEventAttendanceStatus.GOING, None, None
        )
    assert exc_info.value.status_code == 409

    roster = await events.get_attendance_roster(player, team.id, event.id)
    assert roster.is_locked is True


@pytest.mark.asyncio
async def test_nudge_only_pushes_unmarked_and_rate_limits(db_session, monkeypatch) -> None:
    monkeypatch.setattr(push_service, "webpush_async", _fake_webpush_success)

    captain, player, team = await _make_team_with_player(db_session)
    other_player = _make_user()
    db_session.add(other_player)
    await db_session.flush()
    teams = TeamService(db_session)
    # Second player can't join too (one-team-per-user is unrelated) -- just
    # need a second team member, so add them directly via the same flow.
    request = await teams.join_by_code(other_player, team.invite_code)
    await teams.approve_request(captain, request.id)

    db_session.add(_make_subscription(player.id))
    db_session.add(_make_subscription(other_player.id))
    await db_session.flush()

    events = TeamEventService(db_session)
    starts_at = datetime.now(timezone.utc) + timedelta(hours=48)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, starts_at, None)
    await events.set_my_attendance(
        player, team.id, event.id, TeamEventAttendanceStatus.GOING, None, None
    )

    result = await events.send_nudge(captain, team.id, event.id)
    assert result.notified_count == 1  # only other_player is unmarked

    with pytest.raises(HTTPException) as exc_info:
        await events.send_nudge(captain, team.id, event.id)
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_nudge_requires_captain(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    starts_at = datetime.now(timezone.utc) + timedelta(hours=48)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, starts_at, None)

    with pytest.raises(HTTPException) as exc_info:
        await events.send_nudge(player, team.id, event.id)
    assert exc_info.value.status_code == 403
