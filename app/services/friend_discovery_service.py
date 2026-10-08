"""Finding friends beyond the code (2026-10-08): search by first and last
name, teammates, and people friends with my friends.

The name search only ever finds players who are findable_by_name -- their
own choice, or the default from 18 (User.findable_by_name) -- so a kid
isn't found by name unless they turned it on. It needs both names, two
letters each at least, returns ten at most and is rate-limited per user,
so the player list can't be paged through or scraped.
"""
import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.friend import FriendRequest, FriendRequestStatus
from app.models.team import Team, TeamMembership
from app.models.user import ADULT_AGE, User
from app.schemas.friend import FriendRelation, PlayerSuggestionRead

SEARCH_MIN_LETTERS = 2
SEARCH_RESULT_LIMIT = 10
SUGGESTION_LIMIT = 10
SEARCHES_PER_WINDOW = 30
SEARCH_WINDOW_SECONDS = 3600

# Per process: with several workers a user gets that many times the budget,
# which still stops paging through everyone.
_recent_searches: dict[uuid.UUID, deque[float]] = defaultdict(deque)


def _check_search_rate(user_id: uuid.UUID, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    window = _recent_searches[user_id]
    while window and now - window[0] > SEARCH_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= SEARCHES_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ты много искал — передохни пару минут и попробуй снова",
        )
    window.append(now)


def _findable_clause():
    return or_(
        User.name_search.is_(True),
        and_(User.name_search.is_(None), User.age >= ADULT_AGE),
    )


def _normalized(column):
    return func.replace(func.lower(column), "ё", "е")


def _prefix(token: str) -> str:
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{escaped}%"


def search_tokens(query: str) -> tuple[str, str] | None:
    """The first two words, lower-cased with ё as е -- None when the query
    isn't a first and a last name of two letters each yet."""
    words = query.lower().replace("ё", "е").split()
    if len(words) < 2 or any(len(word) < SEARCH_MIN_LETTERS for word in words[:2]):
        return None
    return words[0], words[1]


class FriendDiscoveryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, user: User, query: str) -> list[PlayerSuggestionRead]:
        tokens = search_tokens(query)
        if tokens is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Напиши имя и фамилию — хотя бы по 2 буквы",
            )
        _check_search_rate(user.id)
        first, second = (_prefix(token) for token in tokens)
        first_name, last_name = _normalized(User.first_name), _normalized(User.last_name)
        result = await self._session.execute(
            select(User)
            .where(
                User.id != user.id,
                _findable_clause(),
                or_(
                    and_(first_name.like(first, escape="\\"), last_name.like(second, escape="\\")),
                    and_(first_name.like(second, escape="\\"), last_name.like(first, escape="\\")),
                ),
            )
            .order_by(User.last_name, User.first_name, User.id)
            .limit(SEARCH_RESULT_LIMIT)
        )
        players = list(result.scalars().all())
        return await self._reads(user, players, await self._team_names([p.id for p in players]))

    async def teammates(self, user: User) -> list[PlayerSuggestionRead]:
        """Everyone sharing a team with me, friends left out; each with the
        name of the team we share."""
        mine = select(TeamMembership.team_id).where(TeamMembership.user_id == user.id)
        result = await self._session.execute(
            select(User, Team.name)
            .join(TeamMembership, TeamMembership.user_id == User.id)
            .join(Team, Team.id == TeamMembership.team_id)
            .where(TeamMembership.team_id.in_(mine), User.id != user.id)
            .order_by(Team.name, User.last_name, User.first_name)
        )
        players: list[User] = []
        team_names: dict[uuid.UUID, str] = {}
        for player, team_name in result.all():
            if player.id not in team_names:
                players.append(player)
                team_names[player.id] = team_name
        reads = await self._reads(user, players, team_names)
        return [read for read in reads if read.relation != FriendRelation.FRIEND]

    async def suggestions(self, user: User) -> list[PlayerSuggestionRead]:
        """Friends of my friends, most mutual friends first -- only the
        findable ones (a hidden kid isn't offered to strangers) and not my
        teammates, who have their own list."""
        friend_ids = set(await self._friend_ids(user.id))
        if not friend_ids:
            return []
        mutual = await self._mutual_counts(friend_ids, exclude=friend_ids | {user.id})
        teammates = await self._teammate_ids(user.id)
        candidates = [uid for uid in mutual if uid not in teammates]
        if not candidates:
            return []
        result = await self._session.execute(
            select(User).where(User.id.in_(candidates), _findable_clause())
        )
        players = sorted(
            result.scalars().all(),
            key=lambda p: (-mutual[p.id], p.last_name, p.first_name),
        )[:SUGGESTION_LIMIT]
        return await self._reads(user, players, await self._team_names([p.id for p in players]))

    # -- helpers ---------------------------------------------------------

    async def _reads(
        self, user: User, players: list[User], team_names: dict[uuid.UUID, str]
    ) -> list[PlayerSuggestionRead]:
        if not players:
            return []
        relations = await self._relations(user.id)
        friend_ids = {uid for uid, rel in relations.items() if rel == FriendRelation.FRIEND}
        mutual = await self._mutual_counts(friend_ids, only={p.id for p in players})
        return [
            PlayerSuggestionRead(
                id=player.id,
                first_name=player.first_name,
                last_name=player.last_name,
                avatar_url=player.avatar_url,
                level=player.level,
                jersey_number=player.jersey_number,
                position=player.position,
                team_name=team_names.get(player.id),
                mutual_friends=mutual.get(player.id, 0),
                relation=relations.get(player.id, FriendRelation.NONE),
            )
            for player in players
        ]

    async def _relations(self, user_id: uuid.UUID) -> dict[uuid.UUID, FriendRelation]:
        result = await self._session.execute(
            select(FriendRequest).where(
                FriendRequest.status.in_([FriendRequestStatus.ACCEPTED, FriendRequestStatus.PENDING]),
                or_(FriendRequest.sender_id == user_id, FriendRequest.receiver_id == user_id),
            )
        )
        relations: dict[uuid.UUID, FriendRelation] = {}
        for request in result.scalars().all():
            outgoing = request.sender_id == user_id
            other = request.receiver_id if outgoing else request.sender_id
            if request.status == FriendRequestStatus.ACCEPTED:
                relations[other] = FriendRelation.FRIEND
            elif relations.get(other) != FriendRelation.FRIEND:
                relations[other] = FriendRelation.OUTGOING if outgoing else FriendRelation.INCOMING
        return relations

    async def _friend_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        relations = await self._relations(user_id)
        return [uid for uid, rel in relations.items() if rel == FriendRelation.FRIEND]

    async def _mutual_counts(
        self,
        friend_ids: set[uuid.UUID],
        *,
        only: set[uuid.UUID] | None = None,
        exclude: set[uuid.UUID] | None = None,
    ) -> dict[uuid.UUID, int]:
        """How many of friend_ids each other player is friends with."""
        if not friend_ids:
            return {}
        result = await self._session.execute(
            select(FriendRequest.sender_id, FriendRequest.receiver_id).where(
                FriendRequest.status == FriendRequestStatus.ACCEPTED,
                or_(
                    FriendRequest.sender_id.in_(friend_ids),
                    FriendRequest.receiver_id.in_(friend_ids),
                ),
            )
        )
        counts: dict[uuid.UUID, int] = defaultdict(int)
        for sender_id, receiver_id in result.all():
            for friend, other in ((sender_id, receiver_id), (receiver_id, sender_id)):
                if friend not in friend_ids:
                    continue
                if only is not None and other not in only:
                    continue
                if exclude is not None and other in exclude:
                    continue
                counts[other] += 1
        return dict(counts)

    async def _teammate_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        mine = select(TeamMembership.team_id).where(TeamMembership.user_id == user_id)
        result = await self._session.execute(
            select(TeamMembership.user_id).where(TeamMembership.team_id.in_(mine))
        )
        return set(result.scalars().all())

    async def _team_names(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Each player's first team (by when they joined)."""
        if not user_ids:
            return {}
        result = await self._session.execute(
            select(TeamMembership.user_id, Team.name)
            .join(Team, Team.id == TeamMembership.team_id)
            .where(TeamMembership.user_id.in_(user_ids))
            .order_by(TeamMembership.created_at)
        )
        names: dict[uuid.UUID, str] = {}
        for user_id, name in result.all():
            names.setdefault(user_id, name)
        return names
