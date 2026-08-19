from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.exercise import TargetStat
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
