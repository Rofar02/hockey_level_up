import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import TeamMembership
from app.models.user import User
from app.repositories.friend_repository import FriendRepository
from app.schemas.leaderboard import LeaderboardEntryRead, LeaderboardMeRead
from app.services.progress_service import ProgressService


class LeaderboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._progress = ProgressService(session)
        self._friends = FriendRepository(session)

    async def get_leaderboard(self, limit: int, offset: int) -> list[LeaderboardEntryRead]:
        ranked = await self._ranked_users()
        page = ranked[offset : offset + limit]
        return [self._to_entry(user, rating_excess) for user, rating_excess in page]

    async def get_team_leaderboard(self, team_id: uuid.UUID) -> list[LeaderboardEntryRead]:
        """Same rating_excess ranking as get_leaderboard, filtered to one
        team's members -- no limit/offset, team rosters are small. Resolves
        the roster via TeamMembership itself, then hands a plain user_ids
        list to _ranked_users -- team_id is a Team-specific concept, the
        shared ranking/rating_excess machinery below doesn't need to know
        about it.
        """
        result = await self._session.execute(
            select(TeamMembership.user_id).where(TeamMembership.team_id == team_id)
        )
        user_ids = list(result.scalars().all())
        ranked = await self._ranked_users(user_ids=user_ids)
        return [self._to_entry(user, rating_excess) for user, rating_excess in ranked]

    async def get_friend_leaderboard(self, user: User) -> list[LeaderboardEntryRead]:
        """Same ranking again, filtered to the caller plus their friends --
        no limit/offset, same "small roster" reasoning as get_team_leaderboard.
        Inherits the WHERE age IS NOT NULL filter in _ranked_users like every
        other leaderboard here -- not a new restriction, the existing one.
        """
        friend_ids = await self._friends.list_friend_ids(user.id)
        ranked = await self._ranked_users(user_ids=[user.id, *friend_ids])
        return [self._to_entry(candidate, rating_excess) for candidate, rating_excess in ranked]

    async def get_my_rank(self, user: User) -> LeaderboardMeRead:
        if user.age is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="age is required to appear on the leaderboard",
            )
        ranked = await self._ranked_users()
        for rank, (candidate, rating_excess) in enumerate(ranked, start=1):
            if candidate.id == user.id:
                return LeaderboardMeRead(rank=rank, rating_excess=rating_excess)
        # user.age is set, so the query in _ranked_users always includes
        # them -- this branch is unreachable in practice.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user not ranked")

    async def _ranked_users(self, user_ids: list[uuid.UUID] | None = None) -> list[tuple[User, float]]:
        # Only users with age set can have an expected baseline computed
        # (get_expected_baseline needs it), so they're the only ones
        # eligible for a fair rating_excess.
        query = select(User).where(User.age.is_not(None))
        if user_ids is not None:
            # in_([]) correctly yields zero rows rather than "no filter" --
            # an empty roster (e.g. a team query gone wrong) must never fall
            # back to ranking everyone.
            query = query.where(User.id.in_(user_ids))
        result = await self._session.execute(query.order_by(User.id))
        users = list(result.scalars().all())

        ranked = [(user, await self._progress.get_rating_excess(user)) for user in users]
        ranked.sort(key=lambda pair: pair[1], reverse=True)
        return ranked

    @staticmethod
    def _to_entry(user: User, rating_excess: float) -> LeaderboardEntryRead:
        return LeaderboardEntryRead(
            id=user.id,
            last_name=user.last_name,
            first_name=user.first_name,
            patronymic=user.patronymic,
            avatar_url=user.avatar_url,
            position=user.position,
            jersey_number=user.jersey_number,
            rating_excess=rating_excess,
        )
