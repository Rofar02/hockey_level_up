import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.coach_chat import CoachChatRole


class CoachChatMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class CoachChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: CoachChatRole
    content: str
    created_at: datetime


class CoachChatReplyRead(BaseModel):
    """What POST /users/me/coach-chat returns -- just the assistant's new
    reply, not the whole history (the client already has its own copy of
    the user turn it just sent; GET .../history is for reloading the full
    dialogue)."""

    reply: CoachChatMessageRead
