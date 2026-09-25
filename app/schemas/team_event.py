import uuid
from datetime import datetime
from datetime import time as time_

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
    section_id: uuid.UUID
    order: int
    title: str
    description: str | None = None
    duration_minutes: int | None = None


class TeamEventDrillSectionRead(BaseModel):
    id: uuid.UUID
    order: int
    name: str
    drills: list[TeamEventDrillRead]


class TeamEventRead(BaseModel):
    """Assembled manually in TeamEventService, not from_attributes --
    `sections` is None while the board is a draft and the caller isn't the
    captain (event exists, content hidden), [] once published with no
    sections yet, and populated once they exist. GAME events always get
    board_status=None/sections=None -- games have no board.
    """

    id: uuid.UUID
    team_id: uuid.UUID
    event_type: TeamEventType
    status: TeamEventStatus
    starts_at: datetime
    opponent_name: str | None = None
    board_status: TeamEventPublishStatus | None = None
    sections: list[TeamEventDrillSectionRead] | None = None
    created_at: datetime


class TeamEventCreate(BaseModel):
    event_type: TeamEventType
    starts_at: datetime
    opponent_name: str | None = Field(default=None, max_length=100)


class TeamEventReschedule(BaseModel):
    starts_at: datetime


class TeamEventDrillSectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TeamEventDrillSectionUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TeamEventDrillSectionReorder(BaseModel):
    section_ids: list[uuid.UUID] = Field(min_length=1)


class TeamEventDrillCreate(BaseModel):
    section_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=180)


class TeamEventDrillUpdate(BaseModel):
    # A different section_id moves the drill to the end of that section.
    section_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=180)


class TeamEventDrillReorder(BaseModel):
    """Order within ONE section -- drill_ids must be exactly its drills."""

    section_id: uuid.UUID
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
    """Assembled manually, same visibility contract as TeamEventRead.sections
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


class TeamEventDiaryEntrySave(BaseModel):
    note: str | None = None


class TeamEventDiaryEntryRead(BaseModel):
    note: str | None = None
    created_at: datetime
    updated_at: datetime


class TeamIceScheduleTemplateRead(BaseModel):
    id: uuid.UUID
    weekday: int
    start_time: time_
    active: bool


class TeamIceScheduleTemplateCreate(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time_


class TeamIceScheduleTemplateUpdate(BaseModel):
    active: bool
