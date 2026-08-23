import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.exercise import MovementPattern


class UserTemporaryRestrictionIn(BaseModel):
    movement_pattern: MovementPattern
    reason: str | None = None


class UserTemporaryRestrictionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    movement_pattern: MovementPattern
    reason: str | None
    created_at: datetime
    expires_at: date
    lifted_at: datetime | None
