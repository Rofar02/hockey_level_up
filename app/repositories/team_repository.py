import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team, TeamJoinRequest, TeamJoinRequestStatus, TeamMembership
from app.models.user import User


class TeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- Team --

    async def create_team(self, name: str, owner_id: uuid.UUID, invite_code: str) -> Team:
        team = Team(name=name, owner_id=owner_id, invite_code=invite_code)
        self._session.add(team)
        await self._session.flush()
        return team

    async def get_by_id(self, team_id: uuid.UUID) -> Team | None:
        return await self._session.get(Team, team_id)

    async def get_by_invite_code(self, invite_code: str) -> Team | None:
        result = await self._session.execute(select(Team).where(Team.invite_code == invite_code))
        return result.scalar_one_or_none()

    async def invite_code_exists(self, invite_code: str) -> bool:
        result = await self._session.execute(select(Team.id).where(Team.invite_code == invite_code))
        return result.scalar_one_or_none() is not None

    async def delete_team(self, team: Team) -> None:
        await self._session.delete(team)
        await self._session.flush()

    # -- TeamMembership --

    async def create_membership(self, team_id: uuid.UUID, user_id: uuid.UUID) -> TeamMembership:
        membership = TeamMembership(team_id=team_id, user_id=user_id)
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def get_membership(self, team_id: uuid.UUID, user_id: uuid.UUID) -> TeamMembership | None:
        result = await self._session.execute(
            select(TeamMembership).where(
                TeamMembership.team_id == team_id, TeamMembership.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def delete_membership(self, membership: TeamMembership) -> None:
        await self._session.delete(membership)
        await self._session.flush()

    async def list_memberships_for_user(self, user_id: uuid.UUID) -> list[TeamMembership]:
        result = await self._session.execute(
            select(TeamMembership).where(TeamMembership.user_id == user_id)
        )
        return list(result.scalars().all())

    async def list_members(self, team_id: uuid.UUID) -> list[User]:
        result = await self._session.execute(
            select(User)
            .join(TeamMembership, TeamMembership.user_id == User.id)
            .where(TeamMembership.team_id == team_id)
            .order_by(User.first_name, User.last_name)
        )
        return list(result.scalars().all())

    async def count_members(self, team_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count(TeamMembership.id)).where(TeamMembership.team_id == team_id)
        )
        return result.scalar_one()

    # -- TeamJoinRequest --

    async def create_join_request(self, team_id: uuid.UUID, user_id: uuid.UUID) -> TeamJoinRequest:
        request = TeamJoinRequest(team_id=team_id, user_id=user_id)
        self._session.add(request)
        await self._session.flush()
        return request

    async def get_join_request_by_id(self, request_id: uuid.UUID) -> TeamJoinRequest | None:
        return await self._session.get(TeamJoinRequest, request_id)

    async def get_pending_request(self, team_id: uuid.UUID, user_id: uuid.UUID) -> TeamJoinRequest | None:
        result = await self._session.execute(
            select(TeamJoinRequest).where(
                TeamJoinRequest.team_id == team_id,
                TeamJoinRequest.user_id == user_id,
                TeamJoinRequest.status == TeamJoinRequestStatus.PENDING,
            )
        )
        return result.scalar_one_or_none()

    async def list_pending_for_team(self, team_id: uuid.UUID) -> list[TeamJoinRequest]:
        result = await self._session.execute(
            select(TeamJoinRequest)
            .where(
                TeamJoinRequest.team_id == team_id,
                TeamJoinRequest.status == TeamJoinRequestStatus.PENDING,
            )
            .order_by(TeamJoinRequest.created_at)
        )
        return list(result.scalars().all())

    async def list_pending_for_user(self, user_id: uuid.UUID) -> list[TeamJoinRequest]:
        result = await self._session.execute(
            select(TeamJoinRequest)
            .where(
                TeamJoinRequest.user_id == user_id,
                TeamJoinRequest.status == TeamJoinRequestStatus.PENDING,
            )
            .order_by(TeamJoinRequest.created_at)
        )
        return list(result.scalars().all())

    async def update_join_request_status(
        self, request: TeamJoinRequest, status: TeamJoinRequestStatus
    ) -> TeamJoinRequest:
        request.status = status
        request.decided_at = datetime.now(timezone.utc)
        await self._session.flush()
        return request

    async def delete_join_request(self, request: TeamJoinRequest) -> None:
        await self._session.delete(request)
        await self._session.flush()
