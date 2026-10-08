"""Friend-request pushes (2026-10-08): a request queues "friend_request_sent"
in the outbox, accepting queues "friend_request_accepted"; their handlers
push the other side once, and skip a request that has moved on. No real
push is sent -- webpush_async is monkeypatched, as in
test_report_reminder_scheduler.py; the handlers' own session is swapped for
the test's, so everything rolls back."""
import json
import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app.events.handlers import friend_requests
from app.events.handlers.friend_requests import (
    ACCEPTED_EVENT,
    SENT_EVENT,
    push_friend_request_accepted,
    push_friend_request_sent,
)
from app.models.outbox import OutboxEvent
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services import push_service
from app.services.friend_service import FriendService


async def _user(db_session, first: str, last: str) -> User:
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"push_{unique}",
        email=f"push_{unique}@example.com",
        password_hash="x",
        friend_code=unique.upper(),
        first_name=first,
        last_name=last,
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
        pushes.append({**json.loads(kwargs["data"]), "endpoint": kwargs["subscription_info"]["endpoint"]})
        return "ok"

    @asynccontextmanager
    async def _session():
        yield db_session

    monkeypatch.setattr(push_service, "webpush_async", _fake)
    monkeypatch.setattr(friend_requests, "AsyncSessionLocal", _session)
    return pushes


async def _event(db_session, event_type: str, request_id: uuid.UUID) -> OutboxEvent:
    events = (await db_session.scalars(select(OutboxEvent).where(OutboxEvent.event_type == event_type))).all()
    return next(event for event in events if event.payload["request_id"] == str(request_id))


@pytest.mark.asyncio
async def test_a_request_pushes_the_receiver_once(db_session, sent) -> None:
    sender = await _user(db_session, "Иван", "Петров")
    receiver = await _user(db_session, "Пётр", "Иванов")

    request = await FriendService(db_session).send_request_by_code(sender, receiver.friend_code)
    event = await _event(db_session, SENT_EVENT, request.id)
    await push_friend_request_sent(event.payload, event.id)
    await push_friend_request_sent(event.payload, event.id)  # redelivery

    assert [(p["title"], p["body"], p["url"]) for p in sent] == [
        ("Заявка в друзья", "Иван Петров хочет добавить тебя в друзья", "/friends")
    ]


@pytest.mark.asyncio
async def test_accepting_pushes_the_sender(db_session, sent) -> None:
    sender = await _user(db_session, "Иван", "Петров")
    receiver = await _user(db_session, "Пётр", "Иванов")
    service = FriendService(db_session)
    request = await service.send_request_by_code(sender, receiver.friend_code)

    await service.respond_to_request(receiver, request.id, accept=True)
    event = await _event(db_session, ACCEPTED_EVENT, request.id)
    await push_friend_request_accepted(event.payload, event.id)

    assert [(p["title"], p["body"], p["url"]) for p in sent] == [
        ("Новый друг", "Пётр Иванов принял заявку — теперь вы друзья", f"/profile/{receiver.id}")
    ]


@pytest.mark.asyncio
async def test_asking_back_counts_as_accepting(db_session, sent) -> None:
    first = await _user(db_session, "Иван", "Петров")
    second = await _user(db_session, "Пётр", "Иванов")
    service = FriendService(db_session)
    request = await service.send_request_by_code(first, second.friend_code)

    await service.send_request_by_code(second, first.friend_code)
    event = await _event(db_session, ACCEPTED_EVENT, request.id)
    await push_friend_request_accepted(event.payload, event.id)

    assert [p["body"] for p in sent] == ["Пётр Иванов принял заявку — теперь вы друзья"]


@pytest.mark.asyncio
async def test_an_answered_request_is_not_pushed(db_session, sent) -> None:
    sender = await _user(db_session, "Иван", "Петров")
    receiver = await _user(db_session, "Пётр", "Иванов")
    service = FriendService(db_session)
    request = await service.send_request_by_code(sender, receiver.friend_code)
    await service.respond_to_request(receiver, request.id, accept=False)

    event = await _event(db_session, SENT_EVENT, request.id)
    await push_friend_request_sent(event.payload, event.id)

    assert sent == []
