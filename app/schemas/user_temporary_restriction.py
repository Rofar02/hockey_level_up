import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.exercise import MovementPattern, MuscleGroup


class UserTemporaryRestrictionIn(BaseModel):
    # Exactly one of the two -- mirrors the DB CHECK constraint on
    # UserTemporaryRestriction, enforced here too so a bad request 422s
    # with a clear message instead of surfacing as a raw 500 from the
    # constraint violation.
    movement_pattern: MovementPattern | None = None
    muscle_group: MuscleGroup | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "UserTemporaryRestrictionIn":
        if (self.movement_pattern is None) == (self.muscle_group is None):
            raise ValueError("Specify exactly one of movement_pattern or muscle_group")
        return self


class UserTemporaryRestrictionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    movement_pattern: MovementPattern | None
    muscle_group: MuscleGroup | None
    reason: str | None
    created_at: datetime
    expires_at: date
    lifted_at: datetime | None
