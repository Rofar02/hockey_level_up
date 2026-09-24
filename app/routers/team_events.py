import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.team_event import (
    TeamEventAttendanceRead,
    TeamEventAttendanceRosterRead,
    TeamEventAttendanceSet,
    TeamEventCreate,
    TeamEventDrillCreate,
    TeamEventDrillRead,
    TeamEventDrillReorder,
    TeamEventDrillUpdate,
    TeamEventNudgeResult,
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


@router.get("/{event_id}/attendance", response_model=TeamEventAttendanceRosterRead)
async def get_attendance_roster(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Any team member can see the full roster (going/not_going/unmarked),
    not just the captain -- nothing in the v2 plan restricts this, and
    knowing who else is coming is useful to players too.
    """
    return await TeamEventService(session).get_attendance_roster(current_user, team_id, event_id)


@router.put("/{event_id}/attendance/me", response_model=TeamEventAttendanceRead)
async def set_my_attendance(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    body: TeamEventAttendanceSet,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """409s past the -2h deadline (TeamEventService._require_attendance_open)."""
    return await TeamEventService(session).set_my_attendance(
        current_user, team_id, event_id, body.status, body.reason, body.reason_note
    )


@router.delete("/{event_id}/attendance/me", status_code=status.HTTP_204_NO_CONTENT)
async def clear_my_attendance(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Back to "unmarked" -- also locked past the -2h deadline."""
    await TeamEventService(session).clear_my_attendance(current_user, team_id, event_id)


@router.post("/{event_id}/attendance/nudge", response_model=TeamEventNudgeResult)
async def send_attendance_nudge(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only, rate-limited server-side to once/hour (429 otherwise) --
    pushes everyone still unmarked."""
    return await TeamEventService(session).send_nudge(current_user, team_id, event_id)
