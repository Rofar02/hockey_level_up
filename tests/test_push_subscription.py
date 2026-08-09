"""Web Push foundation: saving/removing PushSubscription rows, and
push_service.send_push's handling of a dead (410) subscription vs a
transient failure. No real push is ever sent -- webpush_async is
monkeypatched at the app.services.push_service module level in every test
that touches send_push.
"""
import uuid

import pytest
from fastapi import HTTPException
from pywebpush import WebPushException
from sqlalchemy import select

from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.schemas.push_subscription import PushSubscriptionCreate, PushSubscriptionKeys
from app.services import push_service
from app.services.push_service import send_push
from app.services.push_subscription_service import PushSubscriptionService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"push_{unique}",
        email=f"push_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_subscription(user_id: uuid.UUID, *, endpoint: str | None = None) -> PushSubscription:
    return PushSubscription(
        id=uuid.uuid4(),
        user_id=user_id,
        endpoint=endpoint or f"https://push.example.com/{uuid.uuid4().hex}",
        p256dh_key="p256dh-test-key",
        auth_key="auth-test-key",
        user_agent="pytest",
    )


class _FakeResponse:
    """Stands in for the aiohttp.ClientResponse WebPushException wraps --
    push_service only ever reads .status off it."""

    def __init__(self, status: int) -> None:
        self.status = status


async def _fake_webpush_success(*_args, **_kwargs) -> str:
    return "ok"


def _fake_webpush_error(status_code: int):
    async def _raise(*_args, **_kwargs):
        raise WebPushException(f"Push failed: {status_code}", response=_FakeResponse(status_code))

    return _raise


# -- saving a subscription --


@pytest.mark.asyncio
async def test_save_creates_a_subscription(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    payload = PushSubscriptionCreate(
        endpoint="https://push.example.com/abc123",
        keys=PushSubscriptionKeys(p256dh="p256dh-value", auth="auth-value"),
    )
    service = PushSubscriptionService(db_session)
    saved = await service.save(user.id, payload, user_agent="Mozilla/5.0 test-agent")

    assert saved.endpoint == "https://push.example.com/abc123"
    assert saved.user_agent == "Mozilla/5.0 test-agent"

    row = (
        await db_session.execute(
            select(PushSubscription).where(PushSubscription.user_id == user.id)
        )
    ).scalar_one()
    assert row.p256dh_key == "p256dh-value"
    assert row.auth_key == "auth-value"


@pytest.mark.asyncio
async def test_save_twice_with_same_endpoint_updates_keys_in_place(db_session) -> None:
    """Re-subscribing from the same device (browser rotated the keys, same
    endpoint) must update, not violate uq_push_subscriptions_user_endpoint."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = PushSubscriptionService(db_session)
    endpoint = "https://push.example.com/same-endpoint"

    await service.save(
        user.id,
        PushSubscriptionCreate(endpoint=endpoint, keys=PushSubscriptionKeys(p256dh="old", auth="old")),
        user_agent="device-A",
    )
    await service.save(
        user.id,
        PushSubscriptionCreate(endpoint=endpoint, keys=PushSubscriptionKeys(p256dh="new", auth="new")),
        user_agent="device-A-updated",
    )

    rows = (
        await db_session.execute(
            select(PushSubscription).where(PushSubscription.user_id == user.id)
        )
    ).scalars().all()
    assert len(rows) == 1  # updated, not duplicated
    assert rows[0].p256dh_key == "new"
    assert rows[0].user_agent == "device-A-updated"


# -- unsubscribing --


@pytest.mark.asyncio
async def test_unsubscribe_removes_the_matching_subscription(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    subscription = _make_subscription(user.id, endpoint="https://push.example.com/to-remove")
    db_session.add(subscription)
    await db_session.flush()

    service = PushSubscriptionService(db_session)
    await service.unsubscribe(user.id, "https://push.example.com/to-remove")

    remaining = (
        await db_session.execute(
            select(PushSubscription).where(PushSubscription.user_id == user.id)
        )
    ).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_unsubscribe_unknown_endpoint_raises_404(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = PushSubscriptionService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.unsubscribe(user.id, "https://push.example.com/never-subscribed")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_unsubscribe_only_removes_the_current_users_subscription(db_session) -> None:
    """Same endpoint string could theoretically collide across users only if
    they share a subscription, which can't happen (unique is per user) --
    this locks in that unsubscribe is scoped by user_id, not endpoint alone."""
    owner = _make_user()
    other = _make_user()
    db_session.add_all([owner, other])
    await db_session.flush()
    endpoint = "https://push.example.com/owned-by-owner"
    db_session.add(_make_subscription(owner.id, endpoint=endpoint))
    await db_session.flush()

    service = PushSubscriptionService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.unsubscribe(other.id, endpoint)
    assert exc_info.value.status_code == 404

    # Owner's row is untouched.
    still_there = (
        await db_session.execute(
            select(PushSubscription).where(PushSubscription.user_id == owner.id)
        )
    ).scalar_one_or_none()
    assert still_there is not None


# -- send_push: 410 handling --


@pytest.mark.asyncio
async def test_send_push_success_keeps_the_subscription(db_session, monkeypatch) -> None:
    monkeypatch.setattr(push_service, "webpush_async", _fake_webpush_success)

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    subscription = _make_subscription(user.id)
    db_session.add(subscription)
    await db_session.flush()

    delivered = await send_push(db_session, subscription, "Title", "Body")

    assert delivered is True
    still_there = await db_session.get(PushSubscription, subscription.id)
    assert still_there is not None


@pytest.mark.asyncio
async def test_send_push_410_deletes_the_subscription(db_session, monkeypatch) -> None:
    monkeypatch.setattr(push_service, "webpush_async", _fake_webpush_error(410))

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    subscription = _make_subscription(user.id)
    db_session.add(subscription)
    await db_session.flush()

    delivered = await send_push(db_session, subscription, "Title", "Body")

    assert delivered is False
    gone = await db_session.get(PushSubscription, subscription.id)
    assert gone is None


@pytest.mark.asyncio
async def test_send_push_non_410_failure_keeps_the_subscription(db_session, monkeypatch) -> None:
    """A 500 (or any non-410) is a transient/server-side failure worth
    retrying later -- must not be treated the same as a dead subscription."""
    monkeypatch.setattr(push_service, "webpush_async", _fake_webpush_error(500))

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    subscription = _make_subscription(user.id)
    db_session.add(subscription)
    await db_session.flush()

    delivered = await send_push(db_session, subscription, "Title", "Body")

    assert delivered is False
    still_there = await db_session.get(PushSubscription, subscription.id)
    assert still_there is not None


@pytest.mark.asyncio
async def test_send_push_malformed_key_data_keeps_the_subscription(db_session, monkeypatch) -> None:
    """pywebpush base64-decodes the subscription's keys before it ever makes
    a request -- bad key data (found live via a smoke test using non-base64
    placeholder keys) raises a plain binascii.Error/ValueError, not a
    WebPushException. Must not crash send_push, and must not be confused
    with a confirmed-dead (410) subscription."""

    async def _raise_decode_error(*_args, **_kwargs):
        raise ValueError("Invalid base64-encoded string")

    monkeypatch.setattr(push_service, "webpush_async", _raise_decode_error)

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    subscription = _make_subscription(user.id)
    db_session.add(subscription)
    await db_session.flush()

    delivered = await send_push(db_session, subscription, "Title", "Body")

    assert delivered is False
    still_there = await db_session.get(PushSubscription, subscription.id)
    assert still_there is not None


# -- send_test_notification orchestration --


@pytest.mark.asyncio
async def test_send_test_notification_reports_partial_delivery_and_prunes_dead_ones(
    db_session, monkeypatch
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    good = _make_subscription(user.id, endpoint="https://push.example.com/good")
    dead = _make_subscription(user.id, endpoint="https://push.example.com/dead")
    db_session.add_all([good, dead])
    await db_session.flush()

    async def _fake(subscription_info, **_kwargs):
        if subscription_info["endpoint"].endswith("/dead"):
            raise WebPushException("Push failed: 410", response=_FakeResponse(410))
        return "ok"

    monkeypatch.setattr(push_service, "webpush_async", _fake)

    service = PushSubscriptionService(db_session)
    total, delivered = await service.send_test_notification(user.id)

    assert (total, delivered) == (2, 1)
    remaining = (
        await db_session.execute(
            select(PushSubscription).where(PushSubscription.user_id == user.id)
        )
    ).scalars().all()
    assert {s.endpoint for s in remaining} == {"https://push.example.com/good"}
