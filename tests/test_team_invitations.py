"""Bringing players into a team (2026-10-08): the invite link's preview,
the captain inviting a friend or a findable player, accepting into the
team, the one-team rule, the attention count, and the pushes for join
requests and invitations (webpush_async monkeypatched, the handlers'
session swapped for the test's)."""
import json
import uuid
from contextlib import asynccontextmanager

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.events.handlers import team_invites
from app.events.handlers.team_invites import (
    INVITE_ACCEPTED_EVENT,
    INVITED_EVENT,
    JOIN_APPROVED_EVENT,
    JOIN_REQUESTED_EVENT,
    push_team_invite_accepted,
    push_team_invited,
    push_team_join_approved,
    push_team_join_requested,
)
from app.models.friend import FriendRequest, FriendRequestStatus
from app.models.outbox import OutboxEvent
from app.models.push_subscription import PushSubscription
from app.models.team import TeamMembership
from app.models.user import User
from app.schemas.team import TeamInviteStatus
from app.services import push_service
from app.services.team_attention_service import TeamAttentionService
from app.services.team_invitation_service import TeamInvitationService
from app.services.team_service import TeamService


async def _user(db_session, first: str, last: str, *, age: int | None = 25) -> User:
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"tinv_{unique}",
        email=f"tinv_{unique}@example.com",
        password_hash="x",
        friend_code=unique.upper(),
        first_name=first,
        last_name=last,
        age=age,
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


@pytest.fixture
def sent(db_session, monkeypatch) -> list[dict]:
    pushes: list[dict] = []

    async def _fake(*_args, **kwargs):
        pushes.append(json.loads(kwargs["data"]))
        return "ok"

    @asynccontextmanager
    async def _session():
        yield db_session

    monkeypatch.setattr(push_service, "webpush_async", _fake)
    monkeypatch.setattr(team_invites, "AsyncSessionLocal", _session)
    return pushes


async def _event(db_session, event_type: str, key: str, value: uuid.UUID) -> OutboxEvent:
    events = (await db_session.scalars(select(OutboxEvent).where(OutboxEvent.event_type == event_type))).all()
    return next(event for event in events if event.payload[key] == str(value))


@pytest.mark.asyncio
async def test_the_link_preview_shows_the_team(db_session) -> None:
    captain = await _user(db_session, "Тренер", "Иванов")
    team = await TeamService(db_session).create_team(captain, "Шторм 2010")

    preview = await TeamInvitationService(db_session).preview(team.invite_code.lower())

    assert (preview.name, preview.member_count, preview.captain_last_name) == ("Шторм 2010", 1, "Иванов")


@pytest.mark.asyncio
async def test_a_join_request_pushes_the_captain_and_approval_the_player(db_session, sent) -> None:
    captain = await _user(db_session, "Тренер", "Иванов")
    player = await _user(db_session, "Иван", "Петров")
    teams = TeamService(db_session)
    team = await teams.create_team(captain, "Шторм 2010")

    request = await teams.join_by_code(player, team.invite_code)
    event = await _event(db_session, JOIN_REQUESTED_EVENT, "request_id", request.id)
    await push_team_join_requested(event.payload, event.id)
    await teams.approve_request(captain, request.id)
    event = await _event(db_session, JOIN_APPROVED_EVENT, "request_id", request.id)
    await push_team_join_approved(event.payload, event.id)

    assert [(p["title"], p["body"], p["url"]) for p in sent] == [
        ("Заявка в команду", "Иван Петров хочет в «Шторм 2010»", f"/teams/{team.id}"),
        ("Ты в команде", "Капитан принял тебя в «Шторм 2010»", f"/teams/{team.id}"),
    ]


@pytest.mark.asyncio
async def test_the_captain_invites_and_accepting_joins_the_team(db_session, sent) -> None:
    captain = await _user(db_session, "Тренер", "Иванов")
    player = await _user(db_session, "Иван", "Петров")
    team = await TeamService(db_session).create_team(captain, "Шторм 2010")
    invitations = TeamInvitationService(db_session)

    invited = await invitations.invite(captain, team.id, player.id)
    assert invited.status == TeamInviteStatus.INVITED
    assert (await TeamAttentionService(db_session).get(player)).team_invitations == 1
    with pytest.raises(HTTPException) as again:
        await invitations.invite(captain, team.id, player.id)
    assert again.value.status_code == 409

    [mine] = await invitations.list_mine(player)
    event = await _event(db_session, INVITED_EVENT, "invitation_id", mine.id)
    await push_team_invited(event.payload, event.id)
    accepted = await invitations.respond(player, mine.id, accept=True)
    event = await _event(db_session, INVITE_ACCEPTED_EVENT, "invitation_id", mine.id)
    await push_team_invite_accepted(event.payload, event.id)

    assert accepted.status == "accepted"
    membership = await db_session.scalar(
        select(TeamMembership).where(TeamMembership.team_id == team.id, TeamMembership.user_id == player.id)
    )
    assert membership is not None
    assert [(p["title"], p["body"]) for p in sent] == [
        ("Приглашение в команду", "Тренер Иванов зовёт тебя в «Шторм 2010»"),
        ("Новый игрок", "Иван Петров принял приглашение в «Шторм 2010»"),
    ]


@pytest.mark.asyncio
async def test_hidden_kids_only_as_friends_and_one_team_at_most(db_session) -> None:
    captain = await _user(db_session, "Тренер", "Иванов")
    kid = await _user(db_session, "Скрытый", "Ребёнок", age=12)
    taken = await _user(db_session, "Занятый", "Игрок")
    teams = TeamService(db_session)
    team = await teams.create_team(captain, "Шторм 2010")
    other_team = await teams.create_team(await _user(db_session, "Другой", "Капитан"), "Барс")
    db_session.add(TeamMembership(team_id=other_team.id, user_id=taken.id))
    await db_session.flush()
    invitations = TeamInvitationService(db_session)

    with pytest.raises(HTTPException) as hidden:
        await invitations.invite(captain, team.id, kid.id)
    assert hidden.value.status_code == 403
    db_session.add(FriendRequest(sender_id=captain.id, receiver_id=kid.id, status=FriendRequestStatus.ACCEPTED))
    await db_session.flush()
    assert (await invitations.invite(captain, team.id, kid.id)).status == TeamInviteStatus.INVITED

    with pytest.raises(HTTPException) as busy:
        await invitations.invite(captain, team.id, taken.id)
    assert busy.value.detail == "Игрок уже в другой команде"

    friends = await invitations.candidates(captain, team.id, None)
    assert {(c.id, c.status) for c in friends} == {(kid.id, TeamInviteStatus.INVITED)}


@pytest.mark.asyncio
async def test_only_the_captain_invites(db_session) -> None:
    captain = await _user(db_session, "Тренер", "Иванов")
    member = await _user(db_session, "Иван", "Петров")
    stranger = await _user(db_session, "Пётр", "Сидоров")
    team = await TeamService(db_session).create_team(captain, "Шторм 2010")

    with pytest.raises(HTTPException) as error:
        await TeamInvitationService(db_session).invite(member, team.id, stranger.id)

    assert error.value.status_code == 403
