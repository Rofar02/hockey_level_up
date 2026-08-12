import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.friend import (
    FriendCodePayload,
    FriendRead,
    FriendRequestRead,
    FriendRequestSentRead,
)
from app.schemas.friend_activity import ActivityFeedEntryRead
from app.schemas.leaderboard import LeaderboardEntryRead
from app.services.friend_activity_service import FriendActivityService
from app.services.friend_service import FriendService
from app.services.leaderboard_service import LeaderboardService

router = APIRouter(prefix="/friends", tags=["friends"])


@router.get("", response_model=list[FriendRead])
async def list_friends(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await FriendService(session).list_friends(current_user.id)


@router.get("/leaderboard", response_model=list[LeaderboardEntryRead])
async def get_friend_leaderboard(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Must stay registered *before* DELETE /{friend_id} below -- "leaderboard"
    would otherwise fail UUID parsing against that route's dynamic segment,
    same "/me"-style landmine documented in routers/teams.py.
    """
    return await LeaderboardService(session).get_friend_leaderboard(current_user)


@router.get("/feed", response_model=list[ActivityFeedEntryRead])
async def get_friend_activity_feed(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Same route-ordering note as /leaderboard above."""
    return await FriendActivityService(session).get_feed(current_user.id, limit, offset)


@router.get("/requests", response_model=list[FriendRequestRead])
async def list_incoming_requests(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Same route-ordering note as /leaderboard above."""
    return await FriendService(session).list_incoming_requests(current_user)


@router.post("/requests", response_model=FriendRequestSentRead)
async def send_friend_request(
    body: FriendCodePayload,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await FriendService(session).send_request_by_code(current_user, body.code)


@router.post("/requests/{request_id}/accept", response_model=FriendRequestRead)
async def accept_friend_request(
    request_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await FriendService(session).respond_to_request(current_user, request_id, accept=True)


@router.post("/requests/{request_id}/decline", response_model=FriendRequestRead)
async def decline_friend_request(
    request_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await FriendService(session).respond_to_request(current_user, request_id, accept=False)


@router.delete("/{friend_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_friend(
    friend_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Registered last -- the dynamic {friend_id} segment above would
    otherwise shadow the literal /leaderboard, /feed, /requests paths.
    """
    await FriendService(session).remove_friend(current_user, friend_id)
