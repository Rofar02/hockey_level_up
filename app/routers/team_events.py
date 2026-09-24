import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.team_event import (
    TeamEventCreate,
    TeamEventDrillCreate,
    TeamEventDrillRead,
    TeamEventDrillReorder,
    TeamEventDrillUpdate,
    TeamEventRead,
)
from app.services.team_event_service import TeamEventService

router = APIRouter(prefix="/teams/{team_id}/events", tags=["team-events"])


@router.post("", response_model=TeamEventRead)
async def create_event(
    team_id: uuid.UUID,
    body: TeamEventCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamEventService(session).create_event(
        current_user, team_id, body.event_type, body.starts_at, body.opponent_name
    )


@router.get("", response_model=list[TeamEventRead])
async def list_events(
    team_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamEventService(session).list_events(current_user, team_id)


@router.get("/{event_id}", response_model=TeamEventRead)
async def get_event(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamEventService(session).get_event(current_user, team_id, event_id)


@router.post("/{event_id}/board/publish", response_model=TeamEventRead)
async def publish_board(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only, TRAINING events only (TeamEventService 409s for a
    game). Idempotent -- publishing an already-published board is a no-op.
    """
    return await TeamEventService(session).publish_board(current_user, team_id, event_id)


@router.post("/{event_id}/drills", response_model=TeamEventDrillRead)
async def add_drill(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    body: TeamEventDrillCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamEventService(session).add_drill(
        current_user, team_id, event_id, body.title, body.description
    )


@router.put("/{event_id}/drills/order", response_model=list[TeamEventDrillRead])
async def reorder_drills(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    body: TeamEventDrillReorder,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Must stay registered *before* PATCH/DELETE /drills/{drill_id} below
    only matters if a route shared this same path+method shape -- it
    doesn't here (different HTTP method), kept first anyway for the same
    "/me"-before-"/{id}" discipline teams.py uses elsewhere in this app.
    """
    return await TeamEventService(session).reorder_drills(
        current_user, team_id, event_id, body.drill_ids
    )


@router.patch("/{event_id}/drills/{drill_id}", response_model=TeamEventDrillRead)
async def update_drill(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    drill_id: uuid.UUID,
    body: TeamEventDrillUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamEventService(session).update_drill(
        current_user, team_id, event_id, drill_id, body.title, body.description
    )


@router.delete("/{event_id}/drills/{drill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_drill(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    drill_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await TeamEventService(session).delete_drill(current_user, team_id, event_id, drill_id)
