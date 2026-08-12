"""LeaderboardService.get_friend_leaderboard -- same rating_excess ranking
as the team/global leaderboards, filtered to the caller plus their friends.
Regression coverage for the team_id -> user_ids refactor lives in
test_team_service.py's existing test_team_leaderboard_filters_to_members_only
(unchanged, still green after this refactor).
"""
import uuid

import pytest

from app.models.exercise import EquipmentType
from app.models.user import User
from app.services.friend_service import FriendService
from app.services.leaderboard_service import LeaderboardService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"fboard_{unique}",
        email=f"fboard_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        friend_code=unique.upper(),
    )
    defaults.update(overrides)
    return User(**defaults)


@pytest.mark.asyncio
async def test_friend_leaderboard_includes_self_and_friends_only(db_session) -> None:
    me = _make_user(age=20)
    friend = _make_user(age=22)
    stranger = _make_user(age=25)
    db_session.add_all([me, friend, stranger])
    await db_session.flush()

    friends_service = FriendService(db_session)
    sent = await friends_service.send_request_by_code(me, friend.friend_code)
    await friends_service.respond_to_request(friend, sent.id, accept=True)

    entries = await LeaderboardService(db_session).get_friend_leaderboard(me)
    assert {e.id for e in entries} == {me.id, friend.id}


@pytest.mark.asyncio
async def test_friend_leaderboard_excludes_ageless_users(db_session) -> None:
    # Same WHERE age IS NOT NULL inherited from _ranked_users as every other
    # leaderboard -- not a new restriction introduced for friends.
    me = _make_user(age=20)
    ageless_friend = _make_user(age=None)
    db_session.add_all([me, ageless_friend])
    await db_session.flush()

    friends_service = FriendService(db_session)
    sent = await friends_service.send_request_by_code(me, ageless_friend.friend_code)
    await friends_service.respond_to_request(ageless_friend, sent.id, accept=True)

    entries = await LeaderboardService(db_session).get_friend_leaderboard(me)
    assert {e.id for e in entries} == {me.id}


@pytest.mark.asyncio
async def test_friend_leaderboard_empty_when_no_friends(db_session) -> None:
    me = _make_user(age=20)
    db_session.add(me)
    await db_session.flush()

    entries = await LeaderboardService(db_session).get_friend_leaderboard(me)
    assert {e.id for e in entries} == {me.id}
