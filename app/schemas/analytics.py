from datetime import date
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


# -- GET /users/me/analytics/overview: the whole Analytics screen --


class AnalyticsInsightRead(BaseModel):
    """One "главное за период" card: a finding plus, when there is one, the
    next step. coach_prompt is the ready question for "Спросить тренера"."""

    kind: Literal["decline", "records", "milestone", "regularity"]
    tone: Literal["good", "warning", "neutral"]
    title: str
    detail: str
    action: Literal["ask_coach", "records"] | None = None
    coach_prompt: str | None = None


class AnalyticsStatRead(BaseModel):
    stat: str
    current_value: float
    delta: float
    # Planned main-part blocks for this stat left undone on past days of
    # the period -- the dates mark the chart, planned is the "из N".
    skipped_dates: list[date]
    planned_blocks: int


class AnalyticsRecordRead(BaseModel):
    exercise_name: str
    unit: Literal["kg", "reps", "seconds"]
    before: float
    after: float
    achieved_on: date


class AnalyticsCalendarDayRead(BaseModel):
    date: date
    status: Literal["done", "team", "skipped", "rest", "future", "none"]


class AnalyticsSkippedExerciseRead(BaseModel):
    exercise_name: str
    count: int


class AnalyticsRegularityRead(BaseModel):
    planned_sessions: int
    completed_sessions: int
    streak_days: int
    # None when the player isn't in a team (or the team had no ice).
    team_going: int | None
    team_total: int | None
    # Four Monday-started weeks ending with the current one.
    calendar: list[AnalyticsCalendarDayRead]
    most_skipped: list[AnalyticsSkippedExerciseRead]


class AnalyticsLoadWeekRead(BaseModel):
    week_start: date
    tonnage_kg: float
    sets: int
    # Share of rated sets marked "тяжело"/"максимум"; None with no ratings.
    hard_share: float | None


class AnalyticsLoadRead(BaseModel):
    weeks: list[AnalyticsLoadWeekRead]
    warning: str | None


class AnalyticsMuscleShareRead(BaseModel):
    group: Literal["legs", "core", "back", "chest_shoulders", "arms"]
    share: float


class AnalyticsBalanceRead(BaseModel):
    groups: list[AnalyticsMuscleShareRead]
    pull_blocks: int
    push_blocks: int
    note: str | None


class AnalyticsOverviewRead(BaseModel):
    days: int
    insights: list[AnalyticsInsightRead]
    stats: list[AnalyticsStatRead]
    records: list[AnalyticsRecordRead]
    regularity: AnalyticsRegularityRead
    load: AnalyticsLoadRead
    balance: AnalyticsBalanceRead
