"""Pushes for joining a team (2026-10-08), through the outbox like the
friend-request ones (see friend_requests.py for the opt-in reasoning):

- team_join_requested -> the captain: someone asked in (link or code);
- team_join_approved -> that player: the captain let them in;
- team_invited -> a player the captain asked in;
- team_invite_accepted -> the captain: that player said yes.

Each is skipped when its request/invitation has moved on by then.
"""
import uuid

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.events.idempotency import try_claim
from app.events.registry import register_handler
from app.models.push_subscription import PushSubscription
from app.models.team import (
    Team,
    TeamInvitation,
    TeamInvitationStatus,
    TeamJoinRequest,
    TeamJoinRequestStatus,
)
from app.models.user import User
from app.services.push_service import send_push

JOIN_REQUESTED_EVENT = "team_join_requested"
JOIN_APPROVED_EVENT = "team_join_approved"
INVITED_EVENT = "team_invited"
INVITE_ACCEPTED_EVENT = "team_invite_accepted"


def _name(user: User | None) -> str:
    if user is None:
        return "Игрок"
    return f"{user.first_name} {user.last_name}".strip() or "Игрок"


async def _push_all(session, user_id: uuid.UUID, title: str, body: str, url: str) -> None:
    subscriptions = (
        await session.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id))
    ).all()
    for subscription in subscriptions:
        await send_push(session, subscription, title, body, url=url)


async def _handle(event_id: uuid.UUID, handler_name: str, build) -> None:
    async with AsyncSessionLocal() as session:
        if not await try_claim(session, event_id, handler_name):
            return
        push = await build(session)
        if push is not None:
            await _push_all(session, *push)
        await session.commit()


@register_handler(JOIN_REQUESTED_EVENT)
async def push_team_join_requested(payload: dict, event_id: uuid.UUID) -> None:
    async def build(session):
        request = await session.get(TeamJoinRequest, uuid.UUID(payload["request_id"]))
        if request is None or request.status != TeamJoinRequestStatus.PENDING:
            return None
        team = await session.get(Team, request.team_id)
        if team is None:
            return None
        player = await session.get(User, request.user_id)
        return (team.owner_id, "Заявка в команду", f"{_name(player)} хочет в «{team.name}»", f"/teams/{team.id}")

    await _handle(event_id, "team_join_requested_push", build)


@register_handler(JOIN_APPROVED_EVENT)
async def push_team_join_approved(payload: dict, event_id: uuid.UUID) -> None:
    async def build(session):
        request = await session.get(TeamJoinRequest, uuid.UUID(payload["request_id"]))
        if request is None or request.status != TeamJoinRequestStatus.APPROVED:
            return None
        team = await session.get(Team, request.team_id)
        if team is None:
            return None
        return (request.user_id, "Ты в команде", f"Капитан принял тебя в «{team.name}»", f"/teams/{team.id}")

    await _handle(event_id, "team_join_approved_push", build)


@register_handler(INVITED_EVENT)
async def push_team_invited(payload: dict, event_id: uuid.UUID) -> None:
    async def build(session):
        invitation = await session.get(TeamInvitation, uuid.UUID(payload["invitation_id"]))
        if invitation is None or invitation.status != TeamInvitationStatus.PENDING:
            return None
        team = await session.get(Team, invitation.team_id)
        if team is None:
            return None
        captain = await session.get(User, invitation.invited_by_id)
        return (invitation.user_id, "Приглашение в команду", f"{_name(captain)} зовёт тебя в «{team.name}»", "/team")

    await _handle(event_id, "team_invited_push", build)


@register_handler(INVITE_ACCEPTED_EVENT)
async def push_team_invite_accepted(payload: dict, event_id: uuid.UUID) -> None:
    async def build(session):
        invitation = await session.get(TeamInvitation, uuid.UUID(payload["invitation_id"]))
        if invitation is None or invitation.status != TeamInvitationStatus.ACCEPTED:
            return None
        team = await session.get(Team, invitation.team_id)
        if team is None:
            return None
        player = await session.get(User, invitation.user_id)
        return (
            invitation.invited_by_id,
            "Новый игрок",
            f"{_name(player)} принял приглашение в «{team.name}»",
            f"/teams/{team.id}",
        )

    await _handle(event_id, "team_invite_accepted_push", build)
