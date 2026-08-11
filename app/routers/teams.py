import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.leaderboard import LeaderboardEntryRead
from app.schemas.team import (
    TeamCreate,
    TeamJoinPayload,
    TeamJoinRequestRead,
    TeamRead,
    TeamSummaryRead,
)
from app.services.team_service import TeamService

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("", response_model=TeamRead)
async def create_team(
    body: TeamCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamService(session).create_team(current_user, body.name)


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
    """members/me rather than a bare "membership", so a future captain-kick
    (DELETE /teams/{team_id}/members/{user_id}) has an obvious, already-
    consistent slot -- not implemented in this pass.
    """
    await TeamService(session).leave_team(current_user, team_id)


@router.get("/{team_id}/leaderboard", response_model=list[LeaderboardEntryRead])
async def get_team_leaderboard(
    team_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamService(session).get_team_leaderboard(current_user, team_id)
