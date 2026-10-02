"""What's waiting for the player on the "Команда" tab -- GET
/users/me/team-attention. Drives the dot on the tab and the "waiting for
you" rows at the top of the team hub. Three counts, each one COUNT query:

- friend_requests -- incoming friend requests not answered yet;
- party_invites -- invitations to a joint training that is still pending
  and not in the past (same filter as the invites list);
- team_join_requests -- requests to join a team the player captains.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.friend import FriendRequest, FriendRequestStatus
from app.models.team import Team, TeamJoinRequest, TeamJoinRequestStatus
from app.models.training_party import (
    TrainingParty,
    TrainingPartyMember,
    TrainingPartyMemberStatus,
    TrainingPartyStatus,
)
from app.models.user import User
from app.schemas.user import TeamAttentionRead


class TeamAttentionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user: User) -> TeamAttentionRead:
        today = datetime.now(ZoneInfo(user.timezone)).date()
        friend_requests = await self._count(
            select(func.count())
            .select_from(FriendRequest)
            .where(
                FriendRequest.receiver_id == user.id,
                FriendRequest.status == FriendRequestStatus.PENDING,
            )
        )
        party_invites = await self._count(
            select(func.count())
            .select_from(TrainingPartyMember)
            .join(TrainingParty, TrainingParty.id == TrainingPartyMember.party_id)
            .where(
                TrainingPartyMember.user_id == user.id,
                TrainingPartyMember.status == TrainingPartyMemberStatus.INVITED,
                TrainingParty.status == TrainingPartyStatus.PENDING,
                TrainingParty.target_date >= today,
            )
        )
        team_join_requests = await self._count(
            select(func.count())
            .select_from(TeamJoinRequest)
            .join(Team, Team.id == TeamJoinRequest.team_id)
            .where(
                Team.owner_id == user.id,
                TeamJoinRequest.status == TeamJoinRequestStatus.PENDING,
            )
        )
        return TeamAttentionRead(
            friend_requests=friend_requests,
            party_invites=party_invites,
            team_join_requests=team_join_requests,
        )

    async def _count(self, statement) -> int:
        return (await self._session.execute(statement)).scalar_one()
