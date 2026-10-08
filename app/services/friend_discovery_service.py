"""Finding friends beyond the code (2026-10-08): search by first and last
name, teammates, and people friends with my friends.

Strangers are only ever found by name when they're findable_by_name --
their own choice, or the default from 18 (User.findable_by_name) -- so a
kid isn't found by name unless they turned it on. Strangers need both
names (one word searches only the people around me, see search()); ten
results at most, rate-limited per user, so the player list can't be paged
through or scraped.
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
# pg_trgm similarity of the whole name for "похожие" (0..1).
SIMILARITY_THRESHOLD = 0.3

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


# A query typed with the keyboard on the wrong layout ("bdfy" for "иван").
_LAYOUT = str.maketrans("qwertyuiop[]asdfghjkl;'zxcvbnm,.`", "йцукенгшщзхъфывапролджэячсмитьбюё")


def query_variants(query: str) -> list[list[str]]:
    """The query's first two words, lower-cased with ё as е, and -- when it
    has Latin letters -- the same keys read on the Russian layout."""
    words = query.lower().replace("ё", "е").split()[:2]
    variants = [words]
    if any("a" <= ch <= "z" for word in words for ch in word):
        variants.append([word.translate(_LAYOUT).replace("ё", "е") for word in words])
    return variants


class FriendDiscoveryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, user: User, query: str) -> list[PlayerSuggestionRead]:
        """Smart search (2026-10-08, owner: "умный поиск").

        - One word: only among the people around me -- friends, teammates,
          anyone with a request either way, and findable friends of my
          friends -- by first or last name. Enough to find "Даня" from the
          team without opening the whole base to a single word.
        - First and last name: everyone findable (and the people around me
          even when they're hidden), either word order.
        - Not enough exact hits: similar spellings by trigram similarity
          ("Питров" -> "Петров"), marked match="similar".
        - A query typed on the English layout is read on the Russian one too.
        """
        variants = query_variants(query)
        words = variants[0]
        if not words or len(words[0]) < SEARCH_MIN_LETTERS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Напиши хотя бы 2 буквы")
        _check_search_rate(user.id)
        full_name = len(words) >= 2 and all(len(word) >= SEARCH_MIN_LETTERS for word in words)

        direct, friends_of_friends = await self._circle(user)
        around_me = or_(User.id.in_(direct), and_(User.id.in_(friends_of_friends), _findable_clause()))
        scope = or_(_findable_clause(), User.id.in_(direct)) if full_name else around_me

        first_name, last_name = _normalized(User.first_name), _normalized(User.last_name)
        matches = []
        for variant in variants:
            if full_name:
                a, b = _prefix(variant[0]), _prefix(variant[1])
                matches.append(
                    or_(
                        and_(first_name.like(a, escape="\\"), last_name.like(b, escape="\\")),
                        and_(first_name.like(b, escape="\\"), last_name.like(a, escape="\\")),
                    )
                )
            else:
                word = _prefix(variant[0])
                matches.append(or_(first_name.like(word, escape="\\"), last_name.like(word, escape="\\")))
        exact = list(
            (
                await self._session.scalars(
                    select(User)
                    .where(User.id != user.id, scope, or_(*matches))
                    .order_by(User.last_name, User.first_name, User.id)
                    .limit(SEARCH_RESULT_LIMIT)
                )
            ).all()
        )

        similar: list[User] = []
        if full_name and len(exact) < SEARCH_RESULT_LIMIT:
            whole = func.concat(first_name, " ", last_name)
            score = func.greatest(*(func.similarity(whole, " ".join(variant)) for variant in variants))
            excluded = [player.id for player in exact] or [uuid.uuid4()]
            similar = list(
                (
                    await self._session.scalars(
                        select(User)
                        .where(User.id != user.id, scope, User.id.not_in(excluded), score >= SIMILARITY_THRESHOLD)
                        .order_by(score.desc(), User.id)
                        .limit(SEARCH_RESULT_LIMIT - len(exact))
                    )
                ).all()
            )

        players = exact + similar
        reads = await self._reads(user, players, await self._team_names([p.id for p in players]))
        similar_ids = {player.id for player in similar}
        return [read.model_copy(update={"match": "similar"}) if read.id in similar_ids else read for read in reads]

    async def player(self, user: User, player_id: uuid.UUID) -> PlayerSuggestionRead:
        """One player as the lists show them -- for the card sheet opened from
        the leaderboard. The caller checks they may see the player."""
        player = await self._session.get(User, player_id)
        if player is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        [read] = await self._reads(user, [player], await self._team_names([player.id]))
        return read

    async def _circle(self, user: User) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
        """The people around me: (friends, teammates and anyone with a
        request either way; friends of my friends). An empty set becomes a
        never-matching dummy id, so the IN clauses stay plain."""
        relations = await self._relations(user.id)
        direct = set(relations) | (await self._teammate_ids(user.id) - {user.id})
        friend_ids = {uid for uid, rel in relations.items() if rel == FriendRelation.FRIEND}
        friends_of_friends = set(await self._mutual_counts(friend_ids, exclude=direct | {user.id}))
        return direct or {uuid.uuid4()}, friends_of_friends or {uuid.uuid4()}

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
