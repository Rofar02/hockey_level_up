"""Pushes for friend requests (2026-10-08): "X хочет добавить тебя в друзья"
to the receiver, "X принял заявку" back to the sender. Through the outbox,
so the request itself never waits on a push service and a restart doesn't
lose one.

Sent to every push subscription the player has -- having one is the opt-in
(reminder_preference is about training reminders only, and NONE is its
default). Skipped when the request has moved on by the time the event is
handled (answered before the push went out, or the friendship removed).
"""
import uuid

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.events.idempotency import try_claim
from app.events.registry import register_handler
from app.models.friend import FriendRequest, FriendRequestStatus
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.push_service import send_push

SENT_EVENT = "friend_request_sent"
ACCEPTED_EVENT = "friend_request_accepted"


def _name(user: User) -> str:
    return f"{user.first_name} {user.last_name}".strip() or "Игрок"


async def _push_all(session, user_id: uuid.UUID, title: str, body: str, url: str) -> None:
    subscriptions = (
        await session.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id))
    ).all()
    for subscription in subscriptions:
        await send_push(session, subscription, title, body, url=url)


@register_handler(SENT_EVENT)
async def push_friend_request_sent(payload: dict, event_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        if not await try_claim(session, event_id, "friend_request_sent_push"):
            return
        request = await session.get(FriendRequest, uuid.UUID(payload["request_id"]))
        if request is None or request.status != FriendRequestStatus.PENDING:
            await session.commit()
            return
        sender = await session.get(User, request.sender_id)
        if sender is not None:
            await _push_all(
                session,
                request.receiver_id,
                "Заявка в друзья",
                f"{_name(sender)} хочет добавить тебя в друзья",
                "/friends",
            )
        await session.commit()


@register_handler(ACCEPTED_EVENT)
async def push_friend_request_accepted(payload: dict, event_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        if not await try_claim(session, event_id, "friend_request_accepted_push"):
            return
        request = await session.get(FriendRequest, uuid.UUID(payload["request_id"]))
        if request is None or request.status != FriendRequestStatus.ACCEPTED:
            await session.commit()
            return
        accepter = await session.get(User, request.receiver_id)
        if accepter is not None:
            await _push_all(
                session,
                request.sender_id,
                "Новый друг",
                f"{_name(accepter)} принял заявку — теперь вы друзья",
                f"/profile/{accepter.id}",
            )
        await session.commit()
