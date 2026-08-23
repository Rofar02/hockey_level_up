import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.schedule import DaySessionType


class TrainingDiaryEntryIn(BaseModel):
    note: str | None = None


class TrainingDiaryEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    training_session_id: uuid.UUID
    note: str | None
    created_at: datetime
    updated_at: datetime


class TrainingDiaryEntryListItem(BaseModel):
    """GET /users/me/training-diary -- includes the day's own date/
    session_type (not on TrainingDiaryEntryRead, since a caller already
    scoped to one session doesn't need it) so the diary list can render
    without a second lookup per entry."""

    id: uuid.UUID
    training_session_id: uuid.UUID
    date: date
    session_type: DaySessionType
    note: str | None
    created_at: datetime
    updated_at: datetime
