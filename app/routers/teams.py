import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user, require_admin
from app.schemas.game_stats import TeamStatsRead, TeamStatsReminderRead
from app.schemas.leaderboard import LeaderboardEntryRead
from app.schemas.team import (
    LeagueRead,
    OtherLeagueNameRead,
    TeamCreate,
    TeamInvitationCreate,
    TeamInvitationRead,
    TeamInviteCandidateRead,
    TeamInvitePreviewRead,
    TeamJoinPayload,
    TeamJoinRequestRead,
    TeamRead,
    TeamScoreRead,
    TeamSummaryRead,
    TeamTransferCaptaincyPayload,
    TeamUpdate,
)
from app.services.game_stats_service import GameStatsService
from app.services.team_invitation_service import TeamInvitationService
from app.services.team_service import TeamService

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("", response_model=TeamRead)
async def create_team(
    body: TeamCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamService(session).create_team(current_user, body.name, body)


@router.get("/leagues", response_model=list[LeagueRead])
async def list_leagues(
    _current_user: Annotated[User, Depends(get_current_user)],
):
    """The fixed league/division list for the create and settings forms
    (app/core/leagues.py). Registered before GET /{team_id}, same "/me"
    landmine as below."""
    return TeamService.list_leagues()


@router.get("/admin/other-leagues", response_model=list[OtherLeagueNameRead])
async def list_other_league_names(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Admin: what captains type into "Другая лига", most frequent first --
    candidates to add to the fixed list."""
    return await TeamService(session).list_other_league_names()


@router.get("/me", response_model=list[TeamSummaryRead])
async def list_my_teams(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Every team the caller belongs to (can be empty). Must stay
    registered *before* GET /{team_id} below: both are 2-segment paths,
    and Starlette matches route-by-route in registration order, so "/me"
    would otherwise be swallowed by {team_id} first and fail UUID parsing
    -- same landmine as skills.py's "/admin" vs "/{skill_id}".
    """
    return await TeamService(session).list_my_teams(current_user)


@router.get("/leaderboard", response_model=list[TeamScoreRead])
async def get_team_rankings(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Cross-team rating (team_score), teams with < 8 members excluded --
    must stay registered *before* GET /{team_id} below, same "/me"-style
    landmine noted there.
    """
    return await TeamService(session).get_team_rankings(limit, offset)


@router.get("/invite/{code}", response_model=TeamInvitePreviewRead)
async def get_team_invite(
    code: str,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """The team behind an invite link (2026-10-08) -- no login needed, the
    page opens for anyone; its members aren't listed. Literal "/invite"
    stays above /{team_id}, same landmine as "/me"."""
    return await TeamInvitationService(session).preview(code)


@router.get("/invitations/me", response_model=list[TeamInvitationRead])
async def list_my_team_invitations(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamInvitationService(session).list_mine(current_user)


@router.post("/invitations/{invitation_id}/accept", response_model=TeamInvitationRead)
async def accept_team_invitation(
    invitation_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamInvitationService(session).respond(current_user, invitation_id, accept=True)


@router.post("/invitations/{invitation_id}/decline", response_model=TeamInvitationRead)
async def decline_team_invitation(
    invitation_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamInvitationService(session).respond(current_user, invitation_id, accept=False)


@router.post("/join", response_model=TeamJoinRequestRead)
async def join_team(
    body: TeamJoinPayload,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamService(session).join_by_code(current_user, body.code)


@router.get("/join-requests/me", response_model=list[TeamJoinRequestRead])
async def list_my_join_requests(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamService(session).list_my_pending_requests(current_user)


@router.delete("/join-requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_join_request(
    request_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await TeamService(session).cancel_pending_request(current_user, request_id)


@router.post("/join-requests/{request_id}/approve", response_model=TeamJoinRequestRead)
async def approve_join_request(
    request_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamService(session).approve_request(current_user, request_id)


@router.post("/join-requests/{request_id}/reject", response_model=TeamJoinRequestRead)
async def reject_join_request(
    request_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamService(session).reject_request(current_user, request_id)


@router.get("/{team_id}", response_model=TeamRead)
async def get_team(
    team_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamService(session).get_team(current_user, team_id)


@router.patch("/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: uuid.UUID,
    body: TeamUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain only: name, city, league, division."""
    return await TeamService(session).update_team(current_user, team_id, body.name, body)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disband_team(
    team_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await TeamService(session).disband_team(current_user, team_id)


@router.post("/{team_id}/logo", response_model=TeamRead)
async def upload_team_logo(
    team_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
):
    """Team emblem -- TeamService.update_logo 403s unless current_user is
    this team's captain (see _require_captain)."""
    return await TeamService(session).update_logo(current_user, team_id, file)


@router.get("/{team_id}/join-requests", response_model=list[TeamJoinRequestRead])
async def list_team_join_requests(
    team_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamService(session).list_pending_requests_for_team(current_user, team_id)


@router.delete("/{team_id}/members/me", status_code=status.HTTP_204_NO_CONTENT)
async def leave_team(
    team_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """members/me rather than a bare "membership", so captain-kick below
    (DELETE /teams/{team_id}/members/{user_id}) has an obvious, already-
    consistent slot.
    """
    await TeamService(session).leave_team(current_user, team_id)


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def kick_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only (TeamService.kick_member 403s otherwise). Must stay
    registered *after* DELETE /{team_id}/members/me above: "me" would
    otherwise fail UUID parsing against this route's {user_id} param --
    same "/me"-style landmine as list_my_teams above.
    """
    await TeamService(session).kick_member(current_user, team_id, user_id)


@router.post("/{team_id}/captain", response_model=TeamRead)
async def transfer_captaincy(
    team_id: uuid.UUID,
    body: TeamTransferCaptaincyPayload,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only -- reassigns Team.owner_id to an existing member."""
    return await TeamService(session).transfer_captaincy(current_user, team_id, body.user_id)


@router.get("/{team_id}/leaderboard", response_model=list[LeaderboardEntryRead])
async def get_team_leaderboard(
    team_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamService(session).get_team_leaderboard(current_user, team_id)


@router.get("/{team_id}/score", response_model=TeamScoreRead)
async def get_team_score(
    team_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """The team's own team_score, visible on its own page regardless of
    whether it has >= 8 members (see get_team_rankings above)."""
    return await TeamService(session).get_team_score(current_user, team_id)


@router.get("/{team_id}/stats", response_model=TeamStatsRead)
async def get_team_stats(
    team_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[Literal["season", "last_game"], Query()] = "season",
):
    """The captain's table: each member's numbers from their own reports on
    this team's games (see GameStatsService)."""
    return await GameStatsService(session).team_stats(current_user, team_id, scope)


@router.post("/{team_id}/stats/remind", response_model=TeamStatsReminderRead)
async def remind_team_reports(
    team_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await GameStatsService(session).remind_missing(current_user, team_id)


@router.get("/{team_id}/invite-candidates", response_model=list[TeamInviteCandidateRead])
async def list_team_invite_candidates(
    team_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    q: str | None = Query(default=None, max_length=100),
):
    """Captain only: their friends, or name-search hits with q."""
    return await TeamInvitationService(session).candidates(current_user, team_id, q)


@router.post("/{team_id}/invitations", response_model=TeamInviteCandidateRead)
async def invite_to_team(
    team_id: uuid.UUID,
    body: TeamInvitationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamInvitationService(session).invite(current_user, team_id, body.user_id)
