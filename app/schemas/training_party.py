import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.exercise import ExerciseRead

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
    # None until the creator confirms an exercise set (see
    # TrainingPartyService.confirm_exercises) -- exercises mirrors it (the
    # shared list every joined member's SessionBlocks were built from, read
    # back from the creator's own materialized blocks) so the frontend can
    # show "what everyone's training" without a separate lookup.
    exercises_finalized_at: datetime | None = None
    exercises: list[ExerciseRead] | None = None


class TrainingPartyExercisesConfirm(BaseModel):
    """POST /training-parties/{id}/exercises/confirm body -- the creator's
    final ordered exercise list, whether it came straight from /suggest
    ("Сгенерировать") or was hand-picked ("Собрать самому"). No mode flag:
    both flows converge on the same "here is the final list" contract, and
    manual mode is intentionally unconstrained (the creator may add/remove
    anything from the full catalog, not just recommended exercises), so
    there's nothing left to validate that differs by mode.
    """

    exercise_ids: list[uuid.UUID] = Field(min_length=1, max_length=12)


class PartyExerciseSuggestionsRead(BaseModel):
    """Response for POST /training-parties/{id}/exercises/suggest -- a fresh,
    non-persisted candidate set from suggest_party_exercises. Calling this
    again ("перемешать") just recomputes; nothing is stored until confirm.
    """

    exercises: list[ExerciseRead]


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
