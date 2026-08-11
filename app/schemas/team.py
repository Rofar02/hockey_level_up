import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.team import TeamJoinRequestStatus
from app.models.user import Position


class TeamMemberRead(BaseModel):
    """Assembled manually in TeamService (not from_attributes) -- a User row
    plus a captain flag computed against the team it's being listed for.
    """

    id: uuid.UUID
    first_name: str
    last_name: str
    avatar_url: str | None = None
    level: int
    jersey_number: int | None = None
    position: Position | None = None
    is_captain: bool


class TeamSummaryRead(BaseModel):
    """One row per team a user belongs to -- GET /teams/me. Assembled
    manually (member_count/is_captain are computed, not raw columns).
    """

    id: uuid.UUID
    name: str
    logo_url: str | None
    member_count: int
    is_captain: bool


class TeamRead(BaseModel):
    """Full detail -- GET /teams/{team_id}. Assembled manually, same
    reasoning as TeamSummaryRead.
    """

    id: uuid.UUID
    name: str
    logo_url: str | None
    invite_code: str
    owner_id: uuid.UUID
    is_captain: bool
    members: list[TeamMemberRead]
    created_at: datetime


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TeamJoinPayload(BaseModel):
    code: str = Field(min_length=1)


class TeamJoinRequestRead(BaseModel):
    """Flat, assembled manually from (TeamJoinRequest, Team, User) --
    reused as-is for both "my own pending requests" (team_name matters,
    the requester fields are just the caller themself) and the captain's
    incoming list (the requester fields matter, team_name is just the
    captain's own team).
    """

    id: uuid.UUID
    team_id: uuid.UUID
    team_name: str
    user_id: uuid.UUID
    first_name: str
    last_name: str
    avatar_url: str | None = None
    status: TeamJoinRequestStatus
    created_at: datetime
