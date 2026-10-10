"""«Как прошёл день» -- see app.services.day_report_service."""
import uuid
from datetime import date

from pydantic import BaseModel

from app.models.exercise import TrainingPhase
from app.models.schedule import DaySessionType
from app.models.set_completion import SetFeedback
from app.models.training_diary import FocusResult, GameResult, IceEffort


class DayReportSetRead(BaseModel):
    weight_kg: float | None = None
    reps: int | None = None
    seconds: int | None = None


class DayReportExerciseRead(BaseModel):
    name: str
    phase: TrainingPhase
    done: bool
    skipped: bool
    sets: list[DayReportSetRead] = []
    feedback: SetFeedback | None = None


class DayReportIceRead(BaseModel):
    skipped: bool
    duration_minutes: int | None = None
    effort: IceEffort | None = None
    focus_title: str | None = None
    focus_result: FocusResult | None = None
    game_result: GameResult | None = None
    goals: int | None = None
    assists: int | None = None
    note: str | None = None


class DayReportTrainingRead(BaseModel):
    day_plan_id: uuid.UUID
    session_type: DaySessionType
    time_of_day: str | None = None
    team_event_id: uuid.UUID | None = None
    exercises_done: int = 0
    exercises_total: int = 0
    sets_total: int = 0
    tonnage_kg: float = 0.0
    # From the first to the last exercise ticked -- None below two.
    minutes: int | None = None
    exercises: list[DayReportExerciseRead] = []
    # Ice / game only, once reported.
    ice: DayReportIceRead | None = None


class DayReportMuscleRead(BaseModel):
    muscle_group: str
    # The map's 0..10 units -- what the day put on this muscle.
    intensity: float


class DayReportStatRead(BaseModel):
    stat: str
    before: float
    after: float


class DayReportRead(BaseModel):
    date: date
    trainings: list[DayReportTrainingRead]
    muscles: list[DayReportMuscleRead]
    stats: list[DayReportStatRead]
    sets_total: int
    tonnage_kg: float
    exercises_done: int
