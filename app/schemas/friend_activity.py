import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.schedule import DaySessionType


class ActivityFeedEntryRead(BaseModel):
    """One outbox_events row (level_up, training_completed, or
    party_completed), reshaped for display -- see
    FriendActivityService.get_feed. type-specific fields (level,
    session_type, party_size) are None when they don't apply to this entry's
    event_type, rather than splitting into three response schemas.
    """

    id: uuid.UUID
    event_type: Literal["level_up", "training_completed", "party_completed"]
    user_id: uuid.UUID
    first_name: str
    last_name: str
    avatar_url: str | None = None
    created_at: datetime
    level: int | None = None
    session_type: DaySessionType | None = None
    party_size: int | None = None
