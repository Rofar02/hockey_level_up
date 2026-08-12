import secrets
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.team import Team, TeamJoinRequest, TeamJoinRequestStatus
from app.models.user import User
from app.repositories.team_repository import TeamRepository
from app.repositories.user_repository import UserRepository
from app.schemas.leaderboard import LeaderboardEntryRead
from app.schemas.team import TeamJoinRequestRead, TeamMemberRead, TeamRead, TeamScoreRead, TeamSummaryRead
from app.services import image_processing
from app.services.leaderboard_service import LeaderboardService
from app.services.team_rating_service import TeamRatingService

_INVITE_CODE_GENERATION_ATTEMPTS = 10
MAX_TEAM_LOGO_SIZE_BYTES = 5 * 1024 * 1024
TEAM_LOGO_TARGET_SIZE = 400


class TeamService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._teams = TeamRepository(session)
        self._users = UserRepository(session)
        self._leaderboard = LeaderboardService(session)
        self._ratings = TeamRatingService(session)

    # -- Team --

    async def create_team(self, user: User, name: str) -> TeamRead:
        invite_code = await self._generate_invite_code()
        team = await self._teams.create_team(name=name, owner_id=user.id, invite_code=invite_code)
        # Captain is always a member too -- keeps list_members simple, no
        # special-casing the owner into the roster separately.
        await self._teams.create_membership(team.id, user.id)
        await self._session.commit()
        return await self._to_team_read(team, user)

    async def _generate_invite_code(self) -> str:
        for _ in range(_INVITE_CODE_GENERATION_ATTEMPTS):
            candidate = secrets.token_hex(4).upper()
            if not await self._teams.invite_code_exists(candidate):
                return candidate
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate a unique invite code",
        )

    async def list_my_teams(self, user: User) -> list[TeamSummaryRead]:
        memberships = await self._teams.list_memberships_for_user(user.id)
        summaries = []
        for membership in memberships:
            team = await self._teams.get_by_id(membership.team_id)
            if team is None:
                continue
            member_count = await self._teams.count_members(team.id)
            summaries.append(
                TeamSummaryRead(
                    id=team.id,
                    name=team.name,
                    logo_url=team.logo_url,
                    member_count=member_count,
                    is_captain=team.owner_id == user.id,
                )
            )
        return summaries

    async def get_team(self, user: User, team_id: uuid.UUID) -> TeamRead:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        return await self._to_team_read(team, user)

    async def update_logo(self, user: User, team_id: uuid.UUID, file: UploadFile) -> TeamRead:
        """Team emblem -- captain only (see _require_captain). Same
        validation/crop/downscale pipeline as User.avatar_path
        (UserService.update_avatar): server-generated filename, never the
        client's, and the previous file is deleted only after the new one
        is committed.
        """
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)

        content = await image_processing.read_limited(file, MAX_TEAM_LOGO_SIZE_BYTES)
        extension = image_processing.detect_image_extension(content)
        image = image_processing.open_oriented(content)

        width, height = image.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        image = image.crop((left, top, left + side, top + side))

        if side > TEAM_LOGO_TARGET_SIZE:
            image = image.resize(
                (TEAM_LOGO_TARGET_SIZE, TEAM_LOGO_TARGET_SIZE), Image.Resampling.LANCZOS
            )

        processed = image_processing.encode(image, extension)

        upload_dir = Path(get_settings().team_logo_upload_dir)
        filename = image_processing.save_new_image_file(upload_dir, processed, extension)

        previous_filename = team.logo_path
        team.logo_path = filename
        await self._session.commit()
        await self._session.refresh(team)

        if previous_filename is not None:
            image_processing.delete_image_file(upload_dir, previous_filename)

        return await self._to_team_read(team, user)

    async def disband_team(self, user: User, team_id: uuid.UUID) -> None:
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        # Cascades TeamMembership and TeamJoinRequest rows via their FKs --
        # nothing else to clean up.
        await self._teams.delete_team(team)
        await self._session.commit()

    # -- membership --

    async def leave_team(self, user: User, team_id: uuid.UUID) -> None:
        team = await self._get_team_or_404(team_id)
        membership = await self._teams.get_membership(team_id, user.id)
        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a member of this team")
        if team.owner_id == user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Captain can't leave -- disband the team instead",
            )
        await self._teams.delete_membership(membership)
        await self._session.commit()

    async def kick_member(self, user: User, team_id: uuid.UUID, target_user_id: uuid.UUID) -> None:
        """Captain-only -- the slot leave_team's docstring above pointed at.
        No re-join ban: a kicked player can immediately rejoin via the
        invite code like anyone else (TeamService.join_by_code), same as if
        they'd left on their own.
        """
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        if target_user_id == team.owner_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Captain can't kick themselves -- transfer captaincy or disband instead",
            )
        membership = await self._teams.get_membership(team_id, target_user_id)
        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a member of this team")
        await self._teams.delete_membership(membership)
        await self._session.commit()

    async def transfer_captaincy(
        self, user: User, team_id: uuid.UUID, new_captain_id: uuid.UUID
    ) -> TeamRead:
        """Captain-only. The new captain must already be a member -- this
        only reassigns Team.owner_id, it doesn't add anyone. The caller's
        own TeamRead.is_captain flips to False in the response, since
        _to_team_read computes it from team.owner_id == requesting_user.id.
        """
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        if new_captain_id == team.owner_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already the captain")
        membership = await self._teams.get_membership(team_id, new_captain_id)
        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a member of this team")
        team.owner_id = new_captain_id
        await self._session.commit()
        await self._session.refresh(team)
        return await self._to_team_read(team, user)

    # -- join requests --

    async def join_by_code(self, user: User, code: str) -> TeamJoinRequestRead:
        team = await self._teams.get_by_invite_code(code)
        if team is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid invite code")
        if await self._teams.get_membership(team.id, user.id) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Already a member of this team"
            )
        if await self._teams.get_pending_request(team.id, user.id) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A join request for this team is already pending",
            )
        request = await self._teams.create_join_request(team.id, user.id)
        await self._session.commit()
        return self._to_join_request_read(request, team=team, requester=user)

    async def list_my_pending_requests(self, user: User) -> list[TeamJoinRequestRead]:
        requests = await self._teams.list_pending_for_user(user.id)
        reads = []
        for request in requests:
            team = await self._teams.get_by_id(request.team_id)
            if team is None:
                continue
            reads.append(self._to_join_request_read(request, team=team, requester=user))
        return reads

    async def cancel_pending_request(self, user: User, request_id: uuid.UUID) -> None:
        request = await self._teams.get_join_request_by_id(request_id)
        if request is None or request.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")
        await self._teams.delete_join_request(request)
        await self._session.commit()

    async def list_pending_requests_for_team(
        self, user: User, team_id: uuid.UUID
    ) -> list[TeamJoinRequestRead]:
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        requests = await self._teams.list_pending_for_team(team_id)
        reads = []
        for request in requests:
            requester = await self._users.get_by_id(request.user_id)
            if requester is None:
                continue
            reads.append(self._to_join_request_read(request, team=team, requester=requester))
        return reads

    async def approve_request(self, user: User, request_id: uuid.UUID) -> TeamJoinRequestRead:
        request, team, requester = await self._get_pending_request_context(user, request_id)
        await self._teams.create_membership(team.id, requester.id)
        await self._teams.update_join_request_status(request, TeamJoinRequestStatus.APPROVED)
        await self._session.commit()
        return self._to_join_request_read(request, team=team, requester=requester)

    async def reject_request(self, user: User, request_id: uuid.UUID) -> TeamJoinRequestRead:
        request, team, requester = await self._get_pending_request_context(user, request_id)
        await self._teams.update_join_request_status(request, TeamJoinRequestStatus.REJECTED)
        await self._session.commit()
        return self._to_join_request_read(request, team=team, requester=requester)

    async def _get_pending_request_context(
        self, user: User, request_id: uuid.UUID
    ) -> tuple[TeamJoinRequest, Team, User]:
        request = await self._teams.get_join_request_by_id(request_id)
        if request is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")
        team = await self._get_team_or_404(request.team_id)
        self._require_captain(user, team)
        requester = await self._users.get_by_id(request.user_id)
        if requester is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requesting user not found")
        return request, team, requester

    # -- leaderboard --

    async def get_team_leaderboard(self, user: User, team_id: uuid.UUID) -> list[LeaderboardEntryRead]:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        return await self._leaderboard.get_team_leaderboard(team_id)

    # -- inter-team rating (team_score) --

    async def get_team_score(self, user: User, team_id: uuid.UUID) -> TeamScoreRead:
        """A team's own score, shown on its own page regardless of whether it
        has enough members to appear in get_team_rankings below.
        """
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        return await self._ratings.compute_team_score(team)

    async def get_team_rankings(self, limit: int, offset: int) -> list[TeamScoreRead]:
        """Cross-team leaderboard -- no membership check, same as the global
        personal /leaderboard: any authenticated user can see it.
        """
        return await self._ratings.get_team_rankings(limit, offset)

    # -- shared helpers --

    async def _get_team_or_404(self, team_id: uuid.UUID) -> Team:
        team = await self._teams.get_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        return team

    async def _require_member(self, user: User, team: Team) -> None:
        if await self._teams.get_membership(team.id, user.id) is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this team")

    @staticmethod
    def _require_captain(user: User, team: Team) -> None:
        if team.owner_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Only the team captain can do this"
            )

    async def _to_team_read(self, team: Team, requesting_user: User) -> TeamRead:
        members = await self._teams.list_members(team.id)
        return TeamRead(
            id=team.id,
            name=team.name,
            logo_url=team.logo_url,
            invite_code=team.invite_code,
            owner_id=team.owner_id,
            is_captain=team.owner_id == requesting_user.id,
            members=[self._to_member_read(member, team) for member in members],
            created_at=team.created_at,
        )

    @staticmethod
    def _to_member_read(member: User, team: Team) -> TeamMemberRead:
        return TeamMemberRead(
            id=member.id,
            first_name=member.first_name,
            last_name=member.last_name,
            avatar_url=member.avatar_url,
            level=member.level,
            jersey_number=member.jersey_number,
            position=member.position,
            is_captain=member.id == team.owner_id,
        )

    @staticmethod
    def _to_join_request_read(
        request: TeamJoinRequest, *, team: Team, requester: User
    ) -> TeamJoinRequestRead:
        return TeamJoinRequestRead(
            id=request.id,
            team_id=team.id,
            team_name=team.name,
            user_id=requester.id,
            first_name=requester.first_name,
            last_name=requester.last_name,
            avatar_url=requester.avatar_url,
            status=request.status,
            created_at=request.created_at,
        )
