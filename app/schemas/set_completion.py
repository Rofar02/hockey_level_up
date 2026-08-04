import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.set_completion import SetFeedback


class SetCompletionCreate(BaseModel):
    exercise_id: uuid.UUID
    training_session_id: uuid.UUID
    set_number: int = Field(ge=1)
    # No gt=0 here on purpose -- the "must be positive when the exercise
    # tracks weight" rule needs a clear 400 message from the service, not a
    # generic pydantic 422, and weight_kg is legitimately None for
    # non-weighted exercises.
    weight_kg: float | None = None
    reps_completed: int | None = Field(default=None, ge=0)
    duration_seconds_completed: int | None = Field(default=None, ge=0)


class SetCompletionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    exercise_id: uuid.UUID
    training_session_id: uuid.UUID
    set_number: int
    weight_kg: float | None
    reps_completed: int | None
    duration_seconds_completed: int | None
    suggested_weight_kg: float | None
    was_weight_adjusted_manually: bool
    feedback: SetFeedback | None
    completed_at: datetime


class SetFeedbackIn(BaseModel):
    exercise_id: uuid.UUID
    training_session_id: uuid.UUID
    feedback: SetFeedback
