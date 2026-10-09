import enum
import uuid
from typing import Literal
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.team import TeamInvitationStatus, TeamJoinRequestStatus
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
    city: str | None = None
    league_name: str | None = None
    division_name: str | None = None


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
    # League and city (2026-10-09) -- raw codes for the settings form, plus
    # display names already resolved from app/core/leagues.py.
    city: str | None = None
    league_code: str = "none"
    division_code: str | None = None
    league_other_name: str | None = None
    league_name: str | None = None
    division_name: str | None = None


class TeamScoreRead(BaseModel):
    """Inter-team rating -- computed on the fly by TeamRatingService, never
    stored (see app/services/team_rating_service.py). All formula components
    are included, not just the final team_score, so the frontend can show a
    breakdown and the formula stays debuggable without re-deriving inputs.
    """

    team_id: uuid.UUID
    team_name: str
    team_score: float
    member_count: int
    sum_xp: int
    avg_trainings_per_member_per_week: float
    activity_bonus: float
    # Place among teams of the same league in the same city -- only on
    # GET /teams/{id}/score, and only when there are at least
    # MIN_TEAMS_FOR_LEAGUE_RANK such teams (app/core/leagues.py).
    league_place: int | None = None
    league_team_count: int | None = None


class TeamCardLeaderRead(BaseModel):
    title: str
    user_id: uuid.UUID
    name: str
    value: str


class TeamCardRead(BaseModel):
    """GET /teams/{id}/card (2026-10-09) -- the team card, open to any
    signed-in player. Games, wins and goals count only games the captain
    entered a score for (TeamEvent.our_score/opponent_score)."""

    id: uuid.UUID
    name: str
    logo_url: str | None
    city: str | None
    league_name: str | None
    division_name: str | None
    member_count: int
    # Average of the members' card "ОБЩИЙ"; None without any stats yet.
    rating: int | None
    league_place: int | None
    league_team_count: int | None
    season_label: str
    games: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    # Share of "иду" marks over the season's past team trainings.
    attendance_percent: int | None
    # Current run of one result: "В3", "П1", "Н2".
    streak: str | None
    leaders: list[TeamCardLeaderRead]
    # The season's most repeated forward line (surnames), release plan
    # step 10 -- None until the same three played together twice.
    most_stable_line: list[str] | None = None
    is_member: bool
    is_captain: bool


class PlayerTeamBadgeRead(BaseModel):
    """The player's team as their card shows it (2026-10-09)."""

    id: uuid.UUID
    name: str
    logo_url: str | None
    city: str | None
    league_name: str | None
    division_name: str | None


class TeamLeagueFields(BaseModel):
    """League/division/city as the create form and the captain's settings
    send them -- cross-field rules (division only for a league that has
    divisions, a name for "other") are checked in TeamService."""

    city: str | None = Field(default=None, max_length=100)
    league_code: str = "none"
    division_code: str | None = None
    league_other_name: str | None = Field(default=None, max_length=100)


class TeamCreate(TeamLeagueFields):
    name: str = Field(min_length=1, max_length=100)


class TeamUpdate(TeamLeagueFields):
    """PATCH /teams/{id} -- the captain's settings form sends every field,
    so a missing optional one means "clear it"."""

    name: str = Field(min_length=1, max_length=100)


class DivisionRead(BaseModel):
    code: str
    name: str


class LeagueRead(BaseModel):
    code: str
    name: str
    divisions: list[DivisionRead]


class OtherLeagueNameRead(BaseModel):
    """Admin: what teams typed into "Другая лига", most frequent first."""

    name: str
    team_count: int


class TeamJoinPayload(BaseModel):
    code: str = Field(min_length=1)


class TeamTransferCaptaincyPayload(BaseModel):
    user_id: uuid.UUID


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


class TeamInvitePreviewRead(BaseModel):
    """GET /teams/invite/{code} (2026-10-08): what the invite link's page
    shows to anyone, logged in or not -- the team, never its members."""

    id: uuid.UUID
    name: str
    logo_url: str | None = None
    member_count: int
    captain_first_name: str
    captain_last_name: str


class TeamInvitationCreate(BaseModel):
    user_id: uuid.UUID


class TeamInviteStatus(str, enum.Enum):
    NONE = "none"
    INVITED = "invited"  # a pending invitation from this team
    MEMBER = "member"  # already in this team
    IN_TEAM = "in_team"  # in another team -- can't be invited


class TeamInviteCandidateRead(BaseModel):
    """A row in the captain's "Пригласить игрока" sheet: a friend, or a
    name-search hit."""

    id: uuid.UUID
    first_name: str
    last_name: str
    avatar_url: str | None = None
    level: int
    jersey_number: int | None = None
    position: Position | None = None
    team_name: str | None = None
    status: TeamInviteStatus
    # A name-search hit by similar spelling (see FriendDiscoveryService.search).
    match: Literal["exact", "similar"] = "exact"


class TeamInvitationRead(BaseModel):
    """An invitation from a captain, as the invited player sees it."""

    id: uuid.UUID
    team_id: uuid.UUID
    team_name: str
    team_logo_url: str | None = None
    member_count: int
    invited_by_first_name: str
    invited_by_last_name: str
    status: TeamInvitationStatus
    created_at: datetime
