from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.exercise import MuscleGroup, TargetStat
from app.models.schedule import DaySessionType


class UserStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stat_type: TargetStat
    current_value: float
    effective_value: float
    trend: Literal["up", "down"]
    idle_days: float
    decay_active: bool
    last_updated_at: datetime


class StatHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stat_type: TargetStat
    value: float
    recorded_at: datetime
    reason: str


class StatHistoryPointRead(BaseModel):
    date: date
    value: float


class MuscleLoadRead(BaseModel):
    """Body-muscles map (2026-08-20 planning session). intensity is the
    already-decayed effective value (0-10), not the raw stored
    current_value -- same "the API never hands back a stale number the
    client would have to decay itself" contract as UserStatRead's
    effective_value. The 5-stage bucketing the plan describes (не
    тренировано/свежая/лёгкая/средняя/перегружена) is deliberately not a
    field here -- it's a pure display concern with no server-side meaning,
    computed client-side from this one float, same as e.g.
    hasExerciseVideo/hasExerciseDescription are pure frontend helpers over
    raw fields rather than server-computed flags."""

    model_config = ConfigDict(from_attributes=True)

    muscle_group: MuscleGroup
    intensity: float
    last_updated_at: datetime


class TrainingStreakRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    current_streak: int
    longest_streak: int
    last_activity_date: date | None


class ActivityCalendarDayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    session_type: DaySessionType
    # Every SessionBlock in the day's session done, at least one exists --
    # same bar app.services.streak_service.is_session_fully_completed uses
    # for streak credit, so the calendar and the streak number never
    # disagree on which days counted.
    fully_completed: bool
