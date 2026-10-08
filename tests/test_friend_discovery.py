"""Finding friends beyond the code (2026-10-08): the name search finds only
the findable (18+ by default, or by choice), needs both names, is
rate-limited; teammates and friends-of-friends lists; a request by id only
to someone those lists could show; the card opens to whoever could find the
player; the invite link resolves to its owner."""
import uuid

import pytest
from fastapi import HTTPException

from app.models.team import TeamMembership
from app.models.friend import FriendRequest, FriendRequestStatus
from app.models.user import User
from app.schemas.friend import FriendRelation
from app.services import friend_discovery_service
from app.services.friend_discovery_service import (
    SEARCHES_PER_WINDOW,
    FriendDiscoveryService,
    _check_search_rate,
    search_tokens,
)
from app.services.friend_service import FriendService
from app.services.team_service import TeamService
from app.services.user_service import UserService


async def _user(db_session, first: str, last: str, *, age: int | None = 25, name_search: bool | None = None) -> User:
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"disc_{unique}",
        email=f"disc_{unique}@example.com",
        password_hash="x",
        friend_code=unique.upper(),
        first_name=first,
        last_name=last,
        age=age,
        name_search=name_search,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _friends(db_session, a: User, b: User) -> None:
    db_session.add(FriendRequest(sender_id=a.id, receiver_id=b.id, status=FriendRequestStatus.ACCEPTED))
    await db_session.flush()


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    friend_discovery_service._recent_searches.clear()
    yield
    friend_discovery_service._recent_searches.clear()


def test_search_needs_two_names_of_two_letters() -> None:
    assert search_tokens("Ив") is None
    assert search_tokens("Иван П") is None
    assert search_tokens("  Иван  Пётр ") == ("иван", "петр")


@pytest.mark.asyncio
async def test_search_finds_adults_and_the_opted_in_but_not_hidden_kids(db_session) -> None:
    surname = f"Шайбов{uuid.uuid4().hex[:6]}"
    me = await _user(db_session, "Я", "Сам")
    adult = await _user(db_session, "Иван", surname)
    kid = await _user(db_session, "Иван", surname, age=14)
    kid_opted_in = await _user(db_session, "Иван", surname, age=15, name_search=True)
    adult_opted_out = await _user(db_session, "Иван", surname, name_search=False)
    unknown_age = await _user(db_session, "Иван", surname, age=None)

    found = await FriendDiscoveryService(db_session).search(me, f"ив {surname[:8]}")
    ids = {player.id for player in found}

    assert adult.id in ids and kid_opted_in.id in ids
    assert not ids & {kid.id, adult_opted_out.id, unknown_age.id}
    # Either word order, ё as е.
    reversed_order = await FriendDiscoveryService(db_session).search(me, f"{surname[:8]} иван")
    assert {player.id for player in reversed_order} == ids


@pytest.mark.asyncio
async def test_search_marks_the_relation(db_session) -> None:
    surname = f"Клюшкин{uuid.uuid4().hex[:6]}"
    me = await _user(db_session, "Я", "Сам")
    friend = await _user(db_session, "Пётр", surname)
    asked = await _user(db_session, "Петр", surname)
    await _friends(db_session, me, friend)
    db_session.add(FriendRequest(sender_id=me.id, receiver_id=asked.id))
    await db_session.flush()

    found = {p.id: p.relation for p in await FriendDiscoveryService(db_session).search(me, f"петр {surname}")}

    assert found == {friend.id: FriendRelation.FRIEND, asked.id: FriendRelation.OUTGOING}


def test_search_is_rate_limited() -> None:
    user_id = uuid.uuid4()
    for second in range(SEARCHES_PER_WINDOW):
        _check_search_rate(user_id, now=float(second))
    with pytest.raises(HTTPException) as error:
        _check_search_rate(user_id, now=float(SEARCHES_PER_WINDOW))
    assert error.value.status_code == 429
    _check_search_rate(user_id, now=4000.0)  # the hour has passed


@pytest.mark.asyncio
async def test_teammates_leave_out_friends_and_carry_the_team(db_session) -> None:
    me = await _user(db_session, "Я", "Сам")
    mate = await _user(db_session, "Даниил", "Ковалёв", age=13)
    friend = await _user(db_session, "Артём", "Лебедев")
    team = await TeamService(db_session).create_team(me, "Шторм 2010")
    for player in (mate, friend):
        db_session.add(TeamMembership(team_id=team.id, user_id=player.id))
    await db_session.flush()
    await _friends(db_session, me, friend)

    rows = await FriendDiscoveryService(db_session).teammates(me)

    assert [(row.id, row.team_name) for row in rows] == [(mate.id, "Шторм 2010")]


@pytest.mark.asyncio
async def test_suggestions_are_findable_friends_of_friends(db_session) -> None:
    me = await _user(db_session, "Я", "Сам")
    a = await _user(db_session, "А", "Друг")
    b = await _user(db_session, "Б", "Друг")
    both = await _user(db_session, "Общий", "Знакомый")
    one = await _user(db_session, "Один", "Знакомый")
    hidden_kid = await _user(db_session, "Скрытый", "Ребёнок", age=12)
    for friend in (a, b):
        await _friends(db_session, me, friend)
    for x, y in ((a, both), (b, both), (a, one), (a, hidden_kid), (a, b)):
        await _friends(db_session, x, y)

    rows = await FriendDiscoveryService(db_session).suggestions(me)

    assert [(row.id, row.mutual_friends) for row in rows] == [(both.id, 2), (one.id, 1)]


@pytest.mark.asyncio
async def test_a_request_by_id_only_to_someone_the_lists_could_show(db_session) -> None:
    me = await _user(db_session, "Я", "Сам")
    adult = await _user(db_session, "Взрослый", "Игрок")
    hidden_kid = await _user(db_session, "Скрытый", "Ребёнок", age=12)
    service = FriendService(db_session)

    sent = await service.send_request_to_user(me, adult.id)
    assert sent.receiver_id == adult.id
    with pytest.raises(HTTPException) as error:
        await service.send_request_to_user(me, hidden_kid.id)
    assert error.value.status_code == 403
    # By the kid's own code (their link) it still works.
    assert (await service.send_request_by_code(me, hidden_kid.friend_code.lower())).receiver_id == hidden_kid.id


@pytest.mark.asyncio
async def test_the_card_opens_to_the_findable_and_both_sides_of_a_request(db_session) -> None:
    me = await _user(db_session, "Я", "Сам")
    adult = await _user(db_session, "Взрослый", "Игрок")
    hidden_kid = await _user(db_session, "Скрытый", "Ребёнок", age=12)
    users = UserService(db_session)

    assert (await users.get_public_profile(me, adult.id)).id == adult.id
    with pytest.raises(HTTPException):
        await users.get_public_profile(me, hidden_kid.id)
    # The kid asks me: now each sees the other's card.
    await FriendService(db_session).send_request_by_code(hidden_kid, me.friend_code)
    assert (await users.get_public_profile(me, hidden_kid.id)).id == hidden_kid.id
