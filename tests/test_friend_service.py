"""FriendService: code-based requests, the reciprocal-duplicate auto-accept
rule, accept/decline, friend list, and removal. Same _make_user shape as
test_team_service.py -- first_name/last_name left unset (server_default=""
populates them on flush), only what each scenario needs is set explicitly.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.exercise import EquipmentType
from app.models.friend import FriendRequestStatus
from app.models.user import User
from app.services.friend_service import FriendService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"friend_{unique}",
        email=f"friend_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        friend_code=unique.upper(),
    )
    defaults.update(overrides)
    return User(**defaults)


@pytest.mark.asyncio
async def test_send_request_by_code_creates_pending_request(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()

    service = FriendService(db_session)
    sent = await service.send_request_by_code(alice, bob.friend_code)

    assert sent.status == FriendRequestStatus.PENDING
    assert sent.receiver_id == bob.id

    incoming = await service.list_incoming_requests(bob)
    assert {r.sender_id for r in incoming} == {alice.id}
    assert incoming[0].status == FriendRequestStatus.PENDING


@pytest.mark.asyncio
async def test_send_request_by_invalid_code_404s(db_session) -> None:
    alice = _make_user()
    db_session.add(alice)
    await db_session.flush()

    service = FriendService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.send_request_by_code(alice, "NOSUCHCODE")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_send_request_to_self_conflicts(db_session) -> None:
    alice = _make_user()
    db_session.add(alice)
    await db_session.flush()

    service = FriendService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.send_request_by_code(alice, alice.friend_code)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_duplicate_pending_request_same_direction_conflicts(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()

    service = FriendService(db_session)
    await service.send_request_by_code(alice, bob.friend_code)

    with pytest.raises(HTTPException) as exc_info:
        await service.send_request_by_code(alice, bob.friend_code)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_reciprocal_request_auto_accepts_instead_of_duplicating(db_session) -> None:
    """Bob already sent Alice a pending request; Alice sending Bob one back
    (via his code) must auto-accept Bob's existing request rather than
    create a second pending row in the other direction.
    """
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()

    service = FriendService(db_session)
    await service.send_request_by_code(bob, alice.friend_code)  # bob -> alice, pending

    sent = await service.send_request_by_code(alice, bob.friend_code)  # alice -> bob
    assert sent.status == FriendRequestStatus.ACCEPTED
    assert sent.receiver_id == bob.id  # the (now-accepted) original bob->alice row

    alice_friends = await service.list_friends(alice.id)
    bob_friends = await service.list_friends(bob.id)
    assert {f.id for f in alice_friends} == {bob.id}
    assert {f.id for f in bob_friends} == {alice.id}

    # No leftover pending request on either side.
    assert await service.list_incoming_requests(alice) == []
    assert await service.list_incoming_requests(bob) == []


@pytest.mark.asyncio
async def test_send_request_when_already_friends_conflicts(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()

    service = FriendService(db_session)
    sent = await service.send_request_by_code(alice, bob.friend_code)
    await service.respond_to_request(bob, sent.id, accept=True)

    with pytest.raises(HTTPException) as exc_info:
        await service.send_request_by_code(alice, bob.friend_code)
    assert exc_info.value.status_code == 409

    with pytest.raises(HTTPException) as exc_info:
        await service.send_request_by_code(bob, alice.friend_code)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_accept_request_makes_both_users_friends(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()

    service = FriendService(db_session)
    sent = await service.send_request_by_code(alice, bob.friend_code)
    accepted = await service.respond_to_request(bob, sent.id, accept=True)

    assert accepted.status == FriendRequestStatus.ACCEPTED
    assert accepted.sender_id == alice.id
    assert {f.id for f in await service.list_friends(alice.id)} == {bob.id}
    assert {f.id for f in await service.list_friends(bob.id)} == {alice.id}


@pytest.mark.asyncio
async def test_decline_request_leaves_sender_unfriended(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()

    service = FriendService(db_session)
    sent = await service.send_request_by_code(alice, bob.friend_code)
    declined = await service.respond_to_request(bob, sent.id, accept=False)

    assert declined.status == FriendRequestStatus.DECLINED
    assert await service.list_friends(alice.id) == []
    assert await service.list_friends(bob.id) == []


@pytest.mark.asyncio
async def test_can_resend_after_decline(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()

    service = FriendService(db_session)
    first = await service.send_request_by_code(alice, bob.friend_code)
    await service.respond_to_request(bob, first.id, accept=False)

    resent = await service.send_request_by_code(alice, bob.friend_code)
    assert resent.status == FriendRequestStatus.PENDING

    accepted = await service.respond_to_request(bob, resent.id, accept=True)
    assert accepted.status == FriendRequestStatus.ACCEPTED


@pytest.mark.asyncio
async def test_respond_requires_being_the_receiver(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    outsider = _make_user()
    db_session.add_all([alice, bob, outsider])
    await db_session.flush()

    service = FriendService(db_session)
    sent = await service.send_request_by_code(alice, bob.friend_code)

    with pytest.raises(HTTPException) as exc_info:
        await service.respond_to_request(outsider, sent.id, accept=True)
    assert exc_info.value.status_code == 403

    # The sender themself isn't the receiver either.
    with pytest.raises(HTTPException) as exc_info:
        await service.respond_to_request(alice, sent.id, accept=True)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_respond_to_already_decided_request_conflicts(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()

    service = FriendService(db_session)
    sent = await service.send_request_by_code(alice, bob.friend_code)
    await service.respond_to_request(bob, sent.id, accept=True)

    with pytest.raises(HTTPException) as exc_info:
        await service.respond_to_request(bob, sent.id, accept=False)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_remove_friend_unfriends_both_ways(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()

    service = FriendService(db_session)
    sent = await service.send_request_by_code(alice, bob.friend_code)
    await service.respond_to_request(bob, sent.id, accept=True)

    await service.remove_friend(alice, bob.id)

    assert await service.list_friends(alice.id) == []
    assert await service.list_friends(bob.id) == []

    # A fresh request afterwards works normally again.
    resent = await service.send_request_by_code(alice, bob.friend_code)
    assert resent.status == FriendRequestStatus.PENDING


@pytest.mark.asyncio
async def test_remove_friend_when_not_friends_404s(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()

    service = FriendService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.remove_friend(alice, bob.id)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_are_friends_reports_correctly(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    carol = _make_user()
    db_session.add_all([alice, bob, carol])
    await db_session.flush()

    service = FriendService(db_session)
    sent = await service.send_request_by_code(alice, bob.friend_code)
    await service.respond_to_request(bob, sent.id, accept=True)

    assert await service.are_friends(alice.id, bob.id) is True
    assert await service.are_friends(bob.id, alice.id) is True
    assert await service.are_friends(alice.id, carol.id) is False
