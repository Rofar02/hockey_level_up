import uuid
from datetime import datetime
from datetime import time as time_

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.team_event import (
    TeamEventAbsenceReason,
    TeamEventAttendanceStatus,
    TeamEventPublishStatus,
    TeamEventStatus,
    TeamEventType,
)
from app.models.user import Position


# -- drill diagram (rink scheme) --
# Coordinates are fractions of the rink (x across, y along; 0..1) so the
# frontend can draw it at any size. Ids are client-generated short strings.

MAX_DIAGRAM_TOKENS = 30
MAX_DIAGRAM_ARROWS = 40
MAX_ARROW_VIA_POINTS = 24
MAX_ARROW_STEP = 20

Coordinate = Field(ge=0, le=1)


class DiagramPoint(BaseModel):
    x: float = Coordinate
    y: float = Coordinate


class DiagramToken(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    # own = our player (letter from position), opponent = neutral marker.
    kind: Literal["own", "opponent", "puck"]
    position: Literal["F", "D", "G"] | None = None
    number: int | None = Field(default=None, ge=0, le=99)
    x: float = Coordinate
    y: float = Coordinate


class DiagramArrow(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    # pass = solid, repass = solid with heads at both ends (the puck goes
    # there and back), shot = double line (always straight, at the goal),
    # skate = dashed (without the puck), skate_puck = wavy.
    kind: Literal["pass", "repass", "shot", "skate", "skate_puck"]
    # When set, the arrow starts at that token and follows it when moved;
    # `start` is still stored so the arrow can be drawn on its own.
    from_token: str | None = Field(default=None, max_length=40)
    start: DiagramPoint
    end: DiagramPoint
    # Points between start and end for a path drawn with a finger (already
    # simplified client-side); the frontend draws a smooth curve through
    # them. Empty = straight arrow, as before.
    via: list[DiagramPoint] = Field(default_factory=list, max_length=MAX_ARROW_VIA_POINTS)
    # Order of play ("такт"): arrows with the same step happen at the same
    # time, a higher step later. None (older schemes) = derived on display:
    # 1 for an arrow from a player, previous arrow's step + 1 for one that
    # continues another arrow.
    step: int | None = Field(default=None, ge=1, le=MAX_ARROW_STEP)


class DrillDiagram(BaseModel):
    tokens: list[DiagramToken] = Field(default_factory=list, max_length=MAX_DIAGRAM_TOKENS)
    arrows: list[DiagramArrow] = Field(default_factory=list, max_length=MAX_DIAGRAM_ARROWS)

    @model_validator(mode="after")
    def _check_references(self) -> "DrillDiagram":
        token_ids = [token.id for token in self.tokens]
        if len(set(token_ids)) != len(token_ids):
            raise ValueError("token ids must be unique")
        arrow_ids = [arrow.id for arrow in self.arrows]
        if len(set(arrow_ids)) != len(arrow_ids):
            raise ValueError("arrow ids must be unique")
        known = set(token_ids)
        for arrow in self.arrows:
            if arrow.from_token is not None and arrow.from_token not in known:
                raise ValueError(f"arrow {arrow.id} starts at unknown token {arrow.from_token}")
        for token in self.tokens:
            if token.kind != "own" and token.position is not None:
                raise ValueError("only own players have a position")
        return self


class TeamEventDrillDiagramSet(BaseModel):
    # null clears the scheme.
    diagram: DrillDiagram | None


class TeamEventDrillRead(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID
    order: int
    title: str
    description: str | None = None
    duration_minutes: int | None = None
    diagram: DrillDiagram | None = None


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
    # GAME only: the final score, once the captain entered it.
    our_score: int | None = None
    opponent_score: int | None = None
    # A joint training seen by a guest team (step 3.5): the host's name.
    host_team_name: str | None = None


class TeamEventCreate(BaseModel):
    event_type: TeamEventType
    starts_at: datetime
    opponent_name: str | None = Field(default=None, max_length=100)


class TeamEventScoreUpdate(BaseModel):
    """PUT /teams/{id}/events/{event_id}/score -- both numbers, or both
    null to clear a wrongly entered score."""

    our_score: int | None = Field(default=None, ge=0, le=99)
    opponent_score: int | None = Field(default=None, ge=0, le=99)


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
    # Set when the drill comes from a coach's template -- the scheme lands
    # in the same write as the drill itself.
    diagram: DrillDiagram | None = None


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
    # 2026-10-09, for the mini-cards: the spot in the group (LW/C/RW,
    # LD/RD, G), the jersey, the level and the card "ОБЩИЙ" with its six
    # stats (the line card averages them).
    slot: str | None = None
    jersey_number: int | None = None
    level: int = 1
    rating: int | None = None
    stats: dict[str, float] = {}


class TeamEventLineupGroupRead(BaseModel):
    id: uuid.UUID
    name: str | None = None
    color: str | None = None
    players: list[TeamEventLineupPlayerRead]
    # Derived from the players' slots: "forwards" (LW/C/RW), "defense"
    # (LD/RD), "goalies" (G) or "mixed" (no slots, or slots of both kinds).
    kind: str = "mixed"
    # Average of the players' ratings.
    rating: int | None = None


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


LINEUP_SLOTS = ("LW", "C", "RW", "LD", "RD", "G")


class TeamEventLineupPlayerAssign(BaseModel):
    group_id: uuid.UUID
    # LW/C/RW, LD/RD or G; None = in the group without a spot.
    slot: str | None = None


class TeamCurrentLineupEventRead(BaseModel):
    id: uuid.UUID
    starts_at: datetime
    opponent_name: str | None = None


class TeamCurrentLineupRead(BaseModel):
    """GET /teams/{id}/lineup/current (2026-10-09): the lineup of the next
    game, or of the last one when none is coming -- None when the team
    has no games at all. lineup.groups is None for a player while the
    captain hasn't published it."""

    event: TeamCurrentLineupEventRead | None = None
    lineup: TeamEventLineupRead | None = None


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


# -- a coach's own drill templates --


class DrillTemplateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=180)
    diagram: DrillDiagram | None = None


class DrillTemplateRename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class DrillTemplateRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    duration_minutes: int | None = None
    diagram: DrillDiagram | None = None
    created_at: datetime
    updated_at: datetime


class TeamReadinessPlayerRead(BaseModel):
    user_id: uuid.UUID
    first_name: str
    last_name: str
    jersey_number: int | None = None
    # "fresh" / "tired" / "overloaded" / "no_data" (release plan step 9).
    status: str


class TeamReadinessRead(BaseModel):
    """GET /teams/{id}/events/{event_id}/readiness -- captain only: the
    "going" players' readiness, by name, without anyone's muscle map."""

    going: int
    fresh: int
    tired: int
    overloaded: int
    no_data: int
    players: list[TeamReadinessPlayerRead]


# -- joint trainings (release plan step 3.5, 2026-10-09) --


class GuestTeamRead(BaseModel):
    team_id: uuid.UUID
    name: str
    logo_url: str | None = None
    # "host", or the guest team's invited / accepted / declined.
    status: str


class GuestInvitationRead(BaseModel):
    """An invitation the guest captain sees: to one training ("event") or
    to a recurring slot ("slot"). `conflict` -- the team already has its
    own training that day; accepting then offers to replace it."""

    id: uuid.UUID
    kind: str
    host_team_id: uuid.UUID
    host_team_name: str
    host_logo_url: str | None = None
    starts_at: datetime | None = None
    slot_label: str | None = None
    conflict: bool = False


class GuestInvitationAnswer(BaseModel):
    accept: bool
    replace_own: bool = False


class GuestTeamInvite(BaseModel):
    team_id: uuid.UUID


class TeamSearchHitRead(BaseModel):
    id: uuid.UUID
    name: str
    logo_url: str | None = None
    city: str | None = None
    league_name: str | None = None
    division_name: str | None = None
