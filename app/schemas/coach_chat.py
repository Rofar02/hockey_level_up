import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.coach_chat import CoachChatRole
from app.models.coach_chat_proposed_action import CoachActionStatus, CoachActionType


class CoachChatMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ProposedActionRead(BaseModel):
    """One coach-proposed action attached to an assistant message -- see
    CoachChatProposedAction. `summary` is a ready-to-render, already
    localized description of what confirming would do (built server-side
    from `action_type`/`payload` by
    CoachChatService._build_action_summary), so the frontend never needs
    its own per-action_type copy dictionary."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action_type: CoachActionType
    payload: dict
    status: CoachActionStatus
    summary: str


class CoachChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: CoachChatRole
    content: str
    created_at: datetime
    proposed_action: ProposedActionRead | None = None


class CoachChatReplyRead(BaseModel):
    """What POST /users/me/coach-chat returns -- just the assistant's new
    reply, not the whole history (the client already has its own copy of
    the user turn it just sent; GET .../history is for reloading the full
    dialogue)."""

    reply: CoachChatMessageRead


class CoachAttentionRead(BaseModel):
    """Why the tab bar's coach button glows (None = it doesn't) -- see
    CoachAttentionService for what each reason means."""

    reason: Literal["pending_action", "checkin", "first_visit"] | None
