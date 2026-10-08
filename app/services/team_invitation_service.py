"""Bringing players into a team (2026-10-08), next to the invite code:

- the invite link /t/CODE: its page shows the team to anyone (preview), and
  "Вступить" is the usual join request the captain approves
  (TeamService.join_by_code);
- the captain asks a particular player -- a friend, or someone found by
  name (only the findable ones, same rule as the friend search) -- and the
  player accepts or declines; accepting puts them straight into the team.

A player is in one team at most, so someone already in a team can't be
invited, and accepting re-checks it.
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.handlers.team_invites import INVITE_ACCEPTED_EVENT, INVITED_EVENT
from app.models.team import Team, TeamInvitation, TeamInvitationStatus, TeamMembership
from app.models.user import User
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.team_repository import TeamRepository
from app.schemas.team import (
    TeamInvitationRead,
    TeamInviteCandidateRead,
    TeamInvitePreviewRead,
    TeamInviteStatus,
)
from app.services.friend_discovery_service import FriendDiscoveryService
from app.services.friend_service import FriendService


class TeamInvitationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._teams = TeamRepository(session)

    async def preview(self, code: str) -> TeamInvitePreviewRead:
        team = await self._teams.get_by_invite_code(code.strip().upper())
        if team is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Приглашение не найдено")
        captain = await self._session.get(User, team.owner_id)
        return TeamInvitePreviewRead(
            id=team.id,
            name=team.name,
            logo_url=team.logo_url,
            member_count=await self._teams.count_members(team.id),
            captain_first_name=captain.first_name if captain is not None else "",
            captain_last_name=captain.last_name if captain is not None else "",
        )

    async def candidates(self, captain: User, team_id: uuid.UUID, query: str | None) -> list[TeamInviteCandidateRead]:
        """Without a query, the captain's friends; with one, the name search
        (its rules and rate limit)."""
        team = await self._captains_team(captain, team_id)
        similar: set[uuid.UUID] = set()
        if query is not None and query.strip():
            hits = await FriendDiscoveryService(self._session).search(captain, query)
            ids = [hit.id for hit in hits]
            similar = {hit.id for hit in hits if hit.match == "similar"}
        else:
            ids = await FriendService(self._session).list_friend_ids(captain.id)
        if not ids:
            return []
        players = {
            player.id: player
            for player in (await self._session.scalars(select(User).where(User.id.in_(ids)))).all()
        }
        memberships = {
            user_id: (member_team_id, name)
            for user_id, member_team_id, name in (
                await self._session.execute(
                    select(TeamMembership.user_id, TeamMembership.team_id, Team.name)
                    .join(Team, Team.id == TeamMembership.team_id)
                    .where(TeamMembership.user_id.in_(ids))
                )
            ).all()
        }
        invited = set(
            (
                await self._session.scalars(
                    select(TeamInvitation.user_id).where(
                        TeamInvitation.team_id == team.id,
                        TeamInvitation.user_id.in_(ids),
                        TeamInvitation.status == TeamInvitationStatus.PENDING,
                    )
                )
            ).all()
        )
        reads = []
        for user_id in ids:
            player = players.get(user_id)
            if player is None:
                continue
            membership = memberships.get(user_id)
            if membership is not None and membership[0] == team.id:
                state = TeamInviteStatus.MEMBER
            elif membership is not None:
                state = TeamInviteStatus.IN_TEAM
            elif user_id in invited:
                state = TeamInviteStatus.INVITED
            else:
                state = TeamInviteStatus.NONE
            reads.append(
                TeamInviteCandidateRead(
                    id=player.id,
                    first_name=player.first_name,
                    last_name=player.last_name,
                    avatar_url=player.avatar_url,
                    level=player.level,
                    jersey_number=player.jersey_number,
                    position=player.position,
                    team_name=membership[1] if membership is not None else None,
                    status=state,
                    match="similar" if user_id in similar else "exact",
                )
            )
        return reads

    async def invite(self, captain: User, team_id: uuid.UUID, user_id: uuid.UUID) -> TeamInviteCandidateRead:
        team = await self._captains_team(captain, team_id)
        player = await self._session.get(User, user_id)
        if player is None or player.id == captain.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Игрок не найден")
        if not (player.findable_by_name or await FriendService(self._session).are_friends(captain.id, player.id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Этого игрока можно позвать только по ссылке на команду",
            )
        membership = await self._teams.get_membership_for_user(player.id)
        if membership is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Игрок уже в этой команде" if membership.team_id == team.id else "Игрок уже в другой команде",
            )
        invitation = await self._session.scalar(
            select(TeamInvitation).where(TeamInvitation.team_id == team.id, TeamInvitation.user_id == player.id)
        )
        if invitation is not None and invitation.status == TeamInvitationStatus.PENDING:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Приглашение уже отправлено")
        if invitation is None:
            invitation = TeamInvitation(team_id=team.id, user_id=player.id, invited_by_id=captain.id)
            self._session.add(invitation)
        else:
            invitation.status = TeamInvitationStatus.PENDING
            invitation.invited_by_id = captain.id
            invitation.created_at = datetime.now(timezone.utc)
            invitation.responded_at = None
        await self._session.flush()
        OutboxRepository(self._session).add(INVITED_EVENT, {"invitation_id": str(invitation.id)})
        await self._session.commit()
        return TeamInviteCandidateRead(
            id=player.id,
            first_name=player.first_name,
            last_name=player.last_name,
            avatar_url=player.avatar_url,
            level=player.level,
            jersey_number=player.jersey_number,
            position=player.position,
            status=TeamInviteStatus.INVITED,
        )

    async def list_mine(self, user: User) -> list[TeamInvitationRead]:
        invitations = (
            await self._session.scalars(
                select(TeamInvitation)
                .where(TeamInvitation.user_id == user.id, TeamInvitation.status == TeamInvitationStatus.PENDING)
                .order_by(TeamInvitation.created_at.desc())
            )
        ).all()
        return [await self._to_read(invitation) for invitation in invitations]

    async def respond(self, user: User, invitation_id: uuid.UUID, accept: bool) -> TeamInvitationRead:
        invitation = await self._session.get(TeamInvitation, invitation_id)
        if invitation is None or invitation.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Приглашение не найдено")
        if invitation.status != TeamInvitationStatus.PENDING:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ты уже ответил на это приглашение")
        if accept:
            if await self._teams.get_membership_for_user(user.id) is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ты уже в команде — сначала выйди из неё",
                )
            await self._teams.create_membership(invitation.team_id, user.id)
            invitation.status = TeamInvitationStatus.ACCEPTED
            OutboxRepository(self._session).add(INVITE_ACCEPTED_EVENT, {"invitation_id": str(invitation.id)})
        else:
            invitation.status = TeamInvitationStatus.DECLINED
        invitation.responded_at = datetime.now(timezone.utc)
        await self._session.commit()
        return await self._to_read(invitation)

    async def _captains_team(self, user: User, team_id: uuid.UUID) -> Team:
        team = await self._teams.get_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        if team.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the team captain can do this")
        return team

    async def _to_read(self, invitation: TeamInvitation) -> TeamInvitationRead:
        team = await self._session.get(Team, invitation.team_id)
        inviter = await self._session.get(User, invitation.invited_by_id)
        return TeamInvitationRead(
            id=invitation.id,
            team_id=invitation.team_id,
            team_name=team.name if team is not None else "",
            team_logo_url=team.logo_url if team is not None else None,
            member_count=await self._teams.count_members(invitation.team_id),
            invited_by_first_name=inviter.first_name if inviter is not None else "",
            invited_by_last_name=inviter.last_name if inviter is not None else "",
            status=invitation.status,
            created_at=invitation.created_at,
        )
