import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

MemberTrainingStatus = Literal[
    "no_plan_for_date", "resting", "game_day", "not_started", "in_progress", "completed"
]
PartyStatus = Literal["pending", "completed", "cancelled", "expired"]


class TrainingPartyCreate(BaseModel):
    target_date: date
    friend_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)


class TrainingPartyMemberRead(BaseModel):
    """training_status/completed_blocks/total_blocks are None for members
    who haven't joined yet (invited/declined) -- nothing to resolve until
    they're actually in. "no_plan_for_date" vs an HTTP error is deliberate
    (see the design discussion): the member's own row carries this same
    value, and the frontend decides the wording ("you" vs "they") since it
    already knows the viewer's own id.
    """

    user_id: uuid.UUID
    first_name: str
    last_name: str
    avatar_url: str | None = None
    membership_status: Literal["invited", "joined", "declined"]
    training_status: MemberTrainingStatus | None = None
    completed_blocks: int | None = None
    total_blocks: int | None = None
    # The member's own DayPlan for target_date, when one exists -- lets the
    # frontend deep-link straight into /training/{day_plan_id} instead of
    # just showing a status label.
    day_plan_id: uuid.UUID | None = None


class TrainingPartyDetailRead(BaseModel):
    id: uuid.UUID
    created_by: uuid.UUID
    target_date: date
    status: PartyStatus
    members: list[TrainingPartyMemberRead]
    created_at: datetime
    completed_at: datetime | None = None


class TrainingPartySummaryRead(BaseModel):
    """One row per party the caller created or joined -- GET /training-parties/me."""

    id: uuid.UUID
    target_date: date
    status: PartyStatus
    member_count: int
    is_creator: bool


class TrainingPartyInviteRead(BaseModel):
    """One row per pending invite sent *to* the caller -- GET /training-parties/invites."""

    party_id: uuid.UUID
    target_date: date
    created_by_id: uuid.UUID
    created_by_first_name: str
    created_by_last_name: str
    created_by_avatar_url: str | None = None
    member_count: int
