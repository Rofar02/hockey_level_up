"""UserService.get_public_profile: 403 unless requester and target are
friends or teammates, and UserPublicRead never carries weight/height (or any
other private field) regardless of what the underlying User row has set --
proven by validating the schema itself, not just by asserting the service
call succeeds, since a missing assertion here wouldn't catch a field
sneaking back onto the schema later.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.exercise import EquipmentType
from app.models.user import User
from app.repositories.team_repository import TeamRepository
from app.schemas.user import UserPublicRead
from app.services.friend_service import FriendService
from app.services.user_service import UserService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"pub_{unique}",
        email=f"pub_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        friend_code=unique.upper(),
        weight=82.5,
        height=181.0,
    )
    defaults.update(overrides)
    return User(**defaults)


@pytest.mark.asyncio
async def test_stranger_gets_403(db_session) -> None:
    me = _make_user()
    stranger = _make_user()
    db_session.add_all([me, stranger])
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await UserService(db_session).get_public_profile(me, stranger.id)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_friend_gets_200_with_reduced_fields(db_session) -> None:
    me = _make_user()
    friend = _make_user(first_name="Ivan", last_name="Petrov")
    db_session.add_all([me, friend])
    await db_session.flush()

    friends_service = FriendService(db_session)
    sent = await friends_service.send_request_by_code(me, friend.friend_code)
    await friends_service.respond_to_request(friend, sent.id, accept=True)

    target = await UserService(db_session).get_public_profile(me, friend.id)
    assert target.id == friend.id

    public = UserPublicRead.model_validate(target)
    assert public.first_name == "Ivan"
    dumped = public.model_dump()
    assert "weight" not in dumped
    assert "height" not in dumped
    assert "email" not in dumped
    assert "is_admin" not in dumped


@pytest.mark.asyncio
async def test_teammate_gets_200(db_session) -> None:
    captain = _make_user()
    teammate = _make_user()
    db_session.add_all([captain, teammate])
    await db_session.flush()

    teams = TeamRepository(db_session)
    team = await teams.create_team(name="Sharks", owner_id=captain.id, invite_code=uuid.uuid4().hex[:16].upper())
    await teams.create_membership(team.id, captain.id)
    await teams.create_membership(team.id, teammate.id)
    await db_session.commit()

    target = await UserService(db_session).get_public_profile(captain, teammate.id)
    assert target.id == teammate.id


@pytest.mark.asyncio
async def test_shared_team_alone_is_not_confused_with_friendship(db_session) -> None:
    # Sanity check that _share_a_team and are_friends are independent checks
    # -- a teammate who is *not* a friend still passes (via the team path),
    # and the profile doesn't require both.
    captain = _make_user()
    teammate = _make_user()
    db_session.add_all([captain, teammate])
    await db_session.flush()

    teams = TeamRepository(db_session)
    team = await teams.create_team(name="Wolves", owner_id=captain.id, invite_code=uuid.uuid4().hex[:16].upper())
    await teams.create_membership(team.id, captain.id)
    await teams.create_membership(team.id, teammate.id)
    await db_session.commit()

    assert await FriendService(db_session).are_friends(captain.id, teammate.id) is False
    # Still viewable -- teammate path alone is sufficient.
    target = await UserService(db_session).get_public_profile(captain, teammate.id)
    assert target.id == teammate.id


@pytest.mark.asyncio
async def test_viewing_own_profile_through_this_path_is_allowed(db_session) -> None:
    me = _make_user()
    db_session.add(me)
    await db_session.flush()

    target = await UserService(db_session).get_public_profile(me, me.id)
    assert target.id == me.id


@pytest.mark.asyncio
async def test_unknown_user_id_404s(db_session) -> None:
    me = _make_user()
    db_session.add(me)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await UserService(db_session).get_public_profile(me, uuid.uuid4())
    assert exc_info.value.status_code == 404
