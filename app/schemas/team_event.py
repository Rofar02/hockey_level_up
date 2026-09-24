import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.team_event import TeamEventPublishStatus, TeamEventStatus, TeamEventType


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


class TeamEventDrillCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


class TeamEventDrillUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


class TeamEventDrillReorder(BaseModel):
    drill_ids: list[uuid.UUID] = Field(min_length=1)
