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
    TeamEventDrillDiagramSet,
    TeamEventDrillRead,
    TeamEventDrillReorder,
    TeamEventDrillSectionCreate,
    TeamEventDrillSectionRead,
    TeamEventDrillSectionReorder,
    TeamEventDrillSectionUpdate,
    TeamEventDrillUpdate,
    TeamEventLineupGroupCreate,
    TeamEventLineupGroupRead,
    TeamEventLineupGroupUpdate,
    TeamEventLineupPlayerAssign,
    TeamEventLineupRead,
    TeamEventNudgeResult,
    TeamEventRead,
    TeamEventReschedule,
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


@router.put("/{event_id}/schedule", response_model=TeamEventRead)
async def reschedule_event(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    body: TeamEventReschedule,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only. Pushes the whole team -- see TeamEventService._push_team."""
    return await TeamEventService(session).reschedule_event(
        current_user, team_id, event_id, body.starts_at
    )


@router.post("/{event_id}/cancel", response_model=TeamEventRead)
async def cancel_event(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only. 409s if already cancelled. Pushes the whole team."""
    return await TeamEventService(session).cancel_event(current_user, team_id, event_id)


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


@router.post("/{event_id}/sections", response_model=TeamEventDrillSectionRead)
async def add_section(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    body: TeamEventDrillSectionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only. The frontend suggests preset names ("Разминка",
    "Броски", ...), the backend accepts any."""
    return await TeamEventService(session).add_section(current_user, team_id, event_id, body.name)


@router.put("/{event_id}/sections/order", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_sections(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    body: TeamEventDrillSectionReorder,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await TeamEventService(session).reorder_sections(current_user, team_id, event_id, body.section_ids)


@router.patch("/{event_id}/sections/{section_id}", response_model=TeamEventDrillSectionRead)
async def rename_section(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    section_id: uuid.UUID,
    body: TeamEventDrillSectionUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamEventService(session).rename_section(
        current_user, team_id, event_id, section_id, body.name
    )


@router.delete("/{event_id}/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_section(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    section_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Deletes the section's drills too."""
    await TeamEventService(session).delete_section(current_user, team_id, event_id, section_id)


@router.post("/{event_id}/drills", response_model=TeamEventDrillRead)
async def add_drill(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    body: TeamEventDrillCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamEventService(session).add_drill(
        current_user,
        team_id,
        event_id,
        body.section_id,
        body.title,
        body.description,
        body.duration_minutes,
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
        current_user, team_id, event_id, body.section_id, body.drill_ids
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
        current_user,
        team_id,
        event_id,
        drill_id,
        body.section_id,
        body.title,
        body.description,
        body.duration_minutes,
    )


@router.put("/{event_id}/drills/{drill_id}/diagram", response_model=TeamEventDrillRead)
async def set_drill_diagram(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    drill_id: uuid.UUID,
    body: TeamEventDrillDiagramSet,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only. Replaces the drill's whole rink scheme; null clears it."""
    return await TeamEventService(session).set_drill_diagram(
        current_user, team_id, event_id, drill_id, body.diagram
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


@router.get("/{event_id}/lineup", response_model=TeamEventLineupRead)
async def get_lineup(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """groups/unassigned are None while the lineup is a draft and the
    caller isn't the captain -- same visibility contract as the board.
    """
    return await TeamEventService(session).get_lineup(current_user, team_id, event_id)


@router.post("/{event_id}/lineup/publish", response_model=TeamEventLineupRead)
async def publish_lineup(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only. Idempotent, same as /board/publish."""
    return await TeamEventService(session).publish_lineup(current_user, team_id, event_id)


@router.post("/{event_id}/lineup/groups", response_model=TeamEventLineupGroupRead)
async def create_lineup_group(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    body: TeamEventLineupGroupCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only. `color` 400s for a GAME event (see TeamEventService
    ._require_color_only_for_training) -- a game's whole team wears one
    jersey, only a training scrimmage needs per-group color.
    """
    return await TeamEventService(session).create_lineup_group(
        current_user, team_id, event_id, body.name, body.color
    )


@router.patch("/{event_id}/lineup/groups/{group_id}", response_model=TeamEventLineupGroupRead)
async def update_lineup_group(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    group_id: uuid.UUID,
    body: TeamEventLineupGroupUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamEventService(session).update_lineup_group(
        current_user, team_id, event_id, group_id, body.name, body.color
    )


@router.delete("/{event_id}/lineup/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lineup_group(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    group_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Its slots cascade -- those players become unassigned, not deleted."""
    await TeamEventService(session).delete_lineup_group(current_user, team_id, event_id, group_id)


@router.put(
    "/{event_id}/lineup/players/{target_user_id}", response_model=TeamEventLineupGroupRead
)
async def assign_lineup_player(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    target_user_id: uuid.UUID,
    body: TeamEventLineupPlayerAssign,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only. Upsert -- moves the player if they were already placed
    in a different group for this event (at most one group per player)."""
    return await TeamEventService(session).assign_player(
        current_user, team_id, event_id, target_user_id, body.group_id
    )


@router.delete(
    "/{event_id}/lineup/players/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def unassign_lineup_player(
    team_id: uuid.UUID,
    event_id: uuid.UUID,
    target_user_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await TeamEventService(session).unassign_player(
        current_user, team_id, event_id, target_user_id
    )
