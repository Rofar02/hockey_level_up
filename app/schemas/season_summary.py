from pydantic import BaseModel

from app.schemas.team import PlayerTeamBadgeRead


class SeasonStatChangeRead(BaseModel):
    stat: str
    before: float
    after: float


class SeasonSummaryRead(BaseModel):
    """GET /users/me/season-summary (2026-10-09, release plan step 10) --
    the «Мой сезон» card. When `available` is false only `reason` and the
    label are filled (unless asked for a preview)."""

    available: bool
    reason: str | None = None
    season_label: str
    ice_days: int = 0
    games: int = 0
    gym_sessions: int = 0
    team_attendance_percent: int | None = None
    stats: list[SeasonStatChangeRead] = []
    overall_before: int | None = None
    overall_after: int | None = None
    best_streak: int = 0
    level: int = 1
    frequent_linemate: str | None = None
    team: PlayerTeamBadgeRead | None = None
