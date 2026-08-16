import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.exercise import TrainingPhase
from app.models.schedule import DaySessionType
from app.schemas.exercise import ExerciseRead


class DayPlanIn(BaseModel):
    date: date
    session_type: DaySessionType
    # ON_ICE only -- rink time is rented in a fixed block, so the caller
    # states it explicitly rather than it falling out of exercise selection
    # (see TrainingSessionRead.duration_seconds for the OFF_ICE side).
    on_ice_minutes: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _on_ice_minutes_only_for_on_ice(self) -> "DayPlanIn":
        if self.on_ice_minutes is not None and self.session_type != DaySessionType.ON_ICE:
            raise ValueError("on_ice_minutes is only valid for session_type=on_ice")
        return self


class WeeklyPlanCreate(BaseModel):
    days: list[DayPlanIn] = Field(min_length=7, max_length=7)


class WeeklyPlanPatch(BaseModel):
    # Partial, unlike creation: only the dates the caller wants to change.
    days: list[DayPlanIn] = Field(min_length=1, max_length=7)


class SessionBlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phase: TrainingPhase
    order: int
    completed_at: datetime | None
    exercise: ExerciseRead


class TrainingSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phase_split: dict[TrainingPhase, float]
    # Honest OFF_ICE estimate (app.core.session_duration) -- for ON_ICE this
    # is still the same estimate of the assembled blocks, not the caller's
    # on_ice_minutes, which is a separately stated rink-time budget, not a
    # content-derived figure.
    duration_seconds: int
    blocks: list[SessionBlockRead]


class DayPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: date
    session_type: DaySessionType
    on_ice_minutes: int | None
    training_session: TrainingSessionRead | None


class WeeklyPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    week_start_date: date
    day_plans: list[DayPlanRead]


class ScheduleConflictRead(BaseModel):
    date: date
    detail: str


class WeeklyPlanPatchResult(BaseModel):
    weekly_plan: WeeklyPlanRead
    conflicts: list[ScheduleConflictRead]
