import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.exercise import TrainingPhase
from app.models.schedule import DaySessionType
from app.schemas.exercise import ExerciseRead


class DayPlanIn(BaseModel):
    date: date
    session_type: DaySessionType


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
    skipped_at: datetime | None
    exercise: ExerciseRead


class TrainingSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phase_split: dict[TrainingPhase, float]
    # Honest estimate of the assembled blocks (app.core.session_duration),
    # for every session_type.
    duration_seconds: int
    blocks: list[SessionBlockRead]


class DayPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: date
    session_type: DaySessionType
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
