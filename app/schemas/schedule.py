import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.exercise import TrainingPhase
from app.models.schedule import DaySessionType
from app.schemas.exercise import ExerciseRead


class DayPlanIn(BaseModel):
    date: date
    session_type: DaySessionType
    # Release plan step 6: on an ice or game day, a separate full gym
    # training in the morning or the evening. Ignored on other days and
    # while settings.double_days_enabled is off.
    extra_gym: Literal["morning", "evening"] | None = None


class PendingReportRead(BaseModel):
    """An ice day or a game that's over without a report (2026-10-10)."""

    day_plan_id: uuid.UUID
    date: date
    session_type: DaySessionType
    team_event_id: uuid.UUID | None = None


class WeeklyPlanCreate(BaseModel):
    days: list[DayPlanIn] = Field(min_length=7, max_length=7)


class WeeklyPlanPatch(BaseModel):
    # Partial, unlike creation: only the dates the caller wants to change.
    days: list[DayPlanIn] = Field(min_length=1, max_length=7)


class CeilingEscalationRead(BaseModel):
    """One bodyweight exercise swapped out after hitting its difficulty
    ceiling (app.services.schedule_service.ScheduleService.
    escalate_ceiling_variant_for_week) -- names only, this is display data
    for SessionCompleteModal's congratulatory card, not a reference to
    reload anything by.
    """

    old_exercise_name: str
    new_exercise_name: str


class SessionBlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phase: TrainingPhase
    order: int
    completed_at: datetime | None
    skipped_at: datetime | None
    exercise: ExerciseRead
    # Populated only by SessionBlockService.complete_block, only when
    # completing *this* block triggered a ceiling escalation -- empty for
    # every other read of a SessionBlockRead (GET plan, replace, skip).
    ceiling_escalations: list[CeilingEscalationRead] = Field(default_factory=list)


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
    # Set while a team event the user marked "going" has taken this day over
    # (see DayPlan.team_event_id).
    team_event_id: uuid.UUID | None = None
    # What the day was before that (2026-10-08: the week page warns when a
    # team event took a gym day, so the player can move the workout).
    replaced_session_type: DaySessionType | None = None
    # Double day (step 6), see DayPlan.is_extra/time_of_day.
    is_extra: bool = False
    time_of_day: str | None = None


class ScheduleFeaturesRead(BaseModel):
    """GET /schedule/features -- optional week features switched on."""

    double_days: bool


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
