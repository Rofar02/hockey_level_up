"""TeamAttentionService: the counts behind the "Команда" tab's dot --
incoming friend requests, pending joint-training invites, and join requests
to teams the player captains (and nobody else's).
"""
import uuid
from datetime import timedelta

import pytest

from app.models.user import User
from app.repositories.team_repository import TeamRepository
from app.schemas.training_party import TrainingPartyCreate
from app.services.friend_service import FriendService
from app.services.team_attention_service import TeamAttentionService
from app.services.training_party_service import TrainingPartyService
from tests.dates import utc_today


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"att_{unique}",
        email=f"att_{unique}@example.com",
        password_hash="irrelevant",
        friend_code=unique.upper(),
    )
    defaults.update(overrides)
    return User(**defaults)


async def _add_users(db_session, count: int) -> list[User]:
    users = [_make_user() for _ in range(count)]
    db_session.add_all(users)
    await db_session.flush()
    return users


@pytest.mark.asyncio
async def test_nothing_waiting(db_session) -> None:
    (me,) = await _add_users(db_session, 1)

    attention = await TeamAttentionService(db_session).get(me)

    assert (attention.friend_requests, attention.party_invites, attention.team_join_requests) == (0, 0, 0)


@pytest.mark.asyncio
async def test_counts_incoming_friend_requests_only(db_session) -> None:
    me, alice, bob = await _add_users(db_session, 3)
    friends = FriendService(db_session)
    await friends.send_request_by_code(alice, me.friend_code)
    await friends.send_request_by_code(bob, me.friend_code)
    # Sent by me -- waiting on someone else, not on me.
    (other,) = await _add_users(db_session, 1)
    await friends.send_request_by_code(me, other.friend_code)

    attention = await TeamAttentionService(db_session).get(me)

    assert attention.friend_requests == 2


@pytest.mark.asyncio
async def test_answered_friend_request_no_longer_counts(db_session) -> None:
    me, alice = await _add_users(db_session, 2)
    friends = FriendService(db_session)
    sent = await friends.send_request_by_code(alice, me.friend_code)
    await friends.respond_to_request(me, sent.id, accept=True)

    attention = await TeamAttentionService(db_session).get(me)

    assert attention.friend_requests == 0


@pytest.mark.asyncio
async def test_counts_pending_party_invites(db_session) -> None:
    me, alice = await _add_users(db_session, 2)
    friends = FriendService(db_session)
    sent = await friends.send_request_by_code(alice, me.friend_code)
    await friends.respond_to_request(me, sent.id, accept=True)
    await TrainingPartyService(db_session).create_party(
        alice, TrainingPartyCreate(target_date=utc_today() + timedelta(days=1), friend_ids=[me.id])
    )

    attention = await TeamAttentionService(db_session).get(me)

    assert attention.party_invites == 1


@pytest.mark.asyncio
async def test_counts_join_requests_only_for_teams_i_captain(db_session) -> None:
    me, player, other_captain = await _add_users(db_session, 3)
    teams = TeamRepository(db_session)
    mine = await teams.create_team(name="Mine", owner_id=me.id, invite_code=uuid.uuid4().hex[:16].upper())
    theirs = await teams.create_team(
        name="Theirs", owner_id=other_captain.id, invite_code=uuid.uuid4().hex[:16].upper()
    )
    await teams.create_join_request(mine.id, player.id)
    await teams.create_join_request(theirs.id, player.id)

    attention = await TeamAttentionService(db_session).get(me)

    assert attention.team_join_requests == 1
