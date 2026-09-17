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
    # 2026-09-17 (audit item #3): whether a TrainingDiaryEntry row exists
    # for this session -- an EXISTS check (app.repositories.
    # training_diary_repository.list_session_ids_with_entries), not
    # note.isnot(None) -- a "quietly skipped" entry (note=None, saved on
    # purpose) still counts as done. Drives TodayCard's "Заполнить
    # дневник" step on the frontend. None for off_ice/rest, the session
    # types TrainingDiaryCard never renders for (see
    # TrainingSessionPage.tsx) -- the diary step just doesn't apply there.
    has_diary_entry: bool | None


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
