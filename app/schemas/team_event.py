import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.team_event import (
    TeamEventAbsenceReason,
    TeamEventAttendanceStatus,
    TeamEventPublishStatus,
    TeamEventStatus,
    TeamEventType,
)
from app.models.user import Position


class TeamEventDrillRead(BaseModel):
    id: uuid.UUID
    order: int
    title: str
    description: str | None = None


class TeamEventRead(BaseModel):
    """Assembled manually in TeamEventService, not from_attributes --
    `drills` is None while the board is a draft and the caller isn't the
    captain (event exists, content hidden), [] once published with no
    cards yet, and populated once cards exist. GAME events always get
    board_status=None/drills=None -- games have no board.
    """

    id: uuid.UUID
    team_id: uuid.UUID
    event_type: TeamEventType
    status: TeamEventStatus
    starts_at: datetime
    opponent_name: str | None = None
    board_status: TeamEventPublishStatus | None = None
    drills: list[TeamEventDrillRead] | None = None
    created_at: datetime


class TeamEventCreate(BaseModel):
    event_type: TeamEventType
    starts_at: datetime
    opponent_name: str | None = Field(default=None, max_length=100)


class TeamEventReschedule(BaseModel):
    starts_at: datetime


class TeamEventDrillCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


class TeamEventDrillUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


class TeamEventDrillReorder(BaseModel):
    drill_ids: list[uuid.UUID] = Field(min_length=1)


class TeamEventAttendanceSet(BaseModel):
    status: TeamEventAttendanceStatus
    reason: TeamEventAbsenceReason | None = None
    reason_note: str | None = None


class TeamEventAttendanceRead(BaseModel):
    status: TeamEventAttendanceStatus
    reason: TeamEventAbsenceReason | None = None
    reason_note: str | None = None
    responded_at: datetime


class TeamEventAttendanceMemberRead(BaseModel):
    """One roster row -- assembled manually in TeamEventService from
    (TeamEventAttendance | None, User). reason/reason_note/responded_at
    stay None for the unmarked group.
    """

    user_id: uuid.UUID
    first_name: str
    last_name: str
    avatar_url: str | None = None
    reason: TeamEventAbsenceReason | None = None
    reason_note: str | None = None
    responded_at: datetime | None = None


class TeamEventAttendanceRosterRead(BaseModel):
    is_locked: bool
    going: list[TeamEventAttendanceMemberRead]
    not_going: list[TeamEventAttendanceMemberRead]
    unmarked: list[TeamEventAttendanceMemberRead]


class TeamEventNudgeResult(BaseModel):
    notified_count: int
    last_nudge_sent_at: datetime


class TeamEventLineupPlayerRead(BaseModel):
    """position is just a UI hint for forming game lines by role -- the
    backend never enforces it (see the v2 plan's section 7).
    """

    user_id: uuid.UUID
    first_name: str
    last_name: str
    avatar_url: str | None = None
    position: Position | None = None


class TeamEventLineupGroupRead(BaseModel):
    id: uuid.UUID
    name: str | None = None
    color: str | None = None
    players: list[TeamEventLineupPlayerRead]


class TeamEventLineupRead(BaseModel):
    """Assembled manually, same visibility contract as TeamEventRead.drills
    -- groups/unassigned are None while the lineup is a draft and the
    caller isn't the captain, populated once published (or always for the
    captain).
    """

    lineup_status: TeamEventPublishStatus
    groups: list[TeamEventLineupGroupRead] | None = None
    unassigned: list[TeamEventLineupPlayerRead] | None = None


class TeamEventLineupGroupCreate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=20)


class TeamEventLineupGroupUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=20)


class TeamEventLineupPlayerAssign(BaseModel):
    group_id: uuid.UUID
