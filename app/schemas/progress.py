from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.exercise import TargetStat


class UserStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stat_type: TargetStat
    current_value: float
    last_updated_at: datetime


class StatHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stat_type: TargetStat
    value: float
    recorded_at: datetime
    reason: str


class TrainingStreakRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    current_streak: int
    longest_streak: int
    last_activity_date: date | None
