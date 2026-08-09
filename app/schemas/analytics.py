from typing import Literal

from pydantic import BaseModel


class AnalyticsMoverRead(BaseModel):
    name: str
    type: Literal["stat", "skill"]
    delta: float
    current_value: float


class AnalyticsMilestoneRead(BaseModel):
    skill_name: str
    points_remaining: float
    threshold: int


class AnalyticsSummaryRead(BaseModel):
    top_gainer: AnalyticsMoverRead
    top_decliner: AnalyticsMoverRead | None
    closest_to_milestone: AnalyticsMilestoneRead | None
    decline_reason: str | None
