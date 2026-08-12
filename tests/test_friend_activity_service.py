"""FriendActivityService.get_feed: reads outbox_events directly (no new
event log), filtered to friends' level_up/training_completed rows only.
Events are seeded directly as OutboxEvent rows here -- this tests the read
side; the write side (that level_up/training_completed actually get
published) is covered by test_level_up_event.py and
test_training_completed_event.py.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.exercise import EquipmentType
from app.models.outbox import OutboxEvent
from app.models.schedule import DaySessionType
from app.models.user import User
from app.services.friend_activity_service import (
    LEVEL_UP_EVENT,
    TRAINING_COMPLETED_EVENT,
    FriendActivityService,
)
from app.services.friend_service import FriendService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"feed_{unique}",
        email=f"feed_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        friend_code=unique.upper(),
        first_name="Feed",
        last_name="User",
    )
    defaults.update(overrides)
    return User(**defaults)


def _level_up_event(user_id: uuid.UUID, *, created_at: datetime) -> OutboxEvent:
    return OutboxEvent(
        event_type=LEVEL_UP_EVENT,
        payload={"user_id": str(user_id), "old_level": 1, "new_level": 2},
        created_at=created_at,
    )


def _training_completed_event(user_id: uuid.UUID, *, created_at: datetime) -> OutboxEvent:
    return OutboxEvent(
        event_type=TRAINING_COMPLETED_EVENT,
        payload={
            "user_id": str(user_id),
            "training_session_id": str(uuid.uuid4()),
            "day_plan_id": str(uuid.uuid4()),
            "session_type": DaySessionType.ON_ICE.value,
        },
        created_at=created_at,
    )


async def _befriend(db_session, a: User, b: User) -> None:
    service = FriendService(db_session)
    sent = await service.send_request_by_code(a, b.friend_code)
    await service.respond_to_request(b, sent.id, accept=True)


@pytest.mark.asyncio
async def test_feed_includes_friend_events_excludes_strangers(db_session) -> None:
    me = _make_user()
    friend = _make_user()
    stranger = _make_user()
    db_session.add_all([me, friend, stranger])
    await db_session.flush()
    await _befriend(db_session, me, friend)

    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            _level_up_event(friend.id, created_at=now),
            _training_completed_event(stranger.id, created_at=now),
        ]
    )
    await db_session.commit()

    feed = await FriendActivityService(db_session).get_feed(me.id, limit=50, offset=0)
    assert len(feed) == 1
    assert feed[0].user_id == friend.id
    assert feed[0].event_type == "level_up"
    assert feed[0].level == 2
    assert feed[0].session_type is None


@pytest.mark.asyncio
async def test_feed_ignores_unrelated_event_types(db_session) -> None:
    me = _make_user()
    friend = _make_user()
    db_session.add_all([me, friend])
    await db_session.flush()
    await _befriend(db_session, me, friend)

    db_session.add(
        OutboxEvent(
            event_type="block_completed",
            payload={"user_id": str(friend.id), "session_block_id": str(uuid.uuid4())},
        )
    )
    await db_session.commit()

    feed = await FriendActivityService(db_session).get_feed(me.id, limit=50, offset=0)
    assert feed == []


@pytest.mark.asyncio
async def test_feed_ordered_newest_first(db_session) -> None:
    me = _make_user()
    friend = _make_user()
    db_session.add_all([me, friend])
    await db_session.flush()
    await _befriend(db_session, me, friend)

    now = datetime.now(timezone.utc)
    older = _level_up_event(friend.id, created_at=now - timedelta(hours=1))
    newer = _training_completed_event(friend.id, created_at=now)
    db_session.add_all([older, newer])
    await db_session.commit()

    feed = await FriendActivityService(db_session).get_feed(me.id, limit=50, offset=0)
    assert [entry.event_type for entry in feed] == ["training_completed", "level_up"]


@pytest.mark.asyncio
async def test_feed_empty_with_no_friends(db_session) -> None:
    me = _make_user()
    db_session.add(me)
    await db_session.flush()

    feed = await FriendActivityService(db_session).get_feed(me.id, limit=50, offset=0)
    assert feed == []
