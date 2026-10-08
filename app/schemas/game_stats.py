import uuid
from datetime import date

from pydantic import BaseModel

from app.models.training_diary import GameResult, GameWorkOn


class SeasonGame(BaseModel):
    date: date
    day_plan_id: uuid.UUID
    result: GameResult
    goals: int | None
    assists: int | None
    shots: int | None
    # The player's own view only (GET /users/me/season).
    self_rating: int | None = None


class SeasonRead(BaseModel):
    """GET /users/me/season -- the player's games this season, from their
    own game reports (2026-10-08). Totals skip a goalie's counter-less
    games; avg_self_rating is the player's own, never shown to anyone else
    here."""

    label: str
    start: date
    end: date
    games: int
    wins: int
    draws: int
    losses: int
    goals: int
    assists: int
    points: int
    shots: int
    avg_self_rating: float | None
    # Oldest first, for the chart and the list (the list shows them newest
    # first itself).
    recent_games: list[SeasonGame]


class TeamPlayerStats(BaseModel):
    user_id: uuid.UUID
    first_name: str
    last_name: str
    jersey_number: int | None
    games: int
    goals: int
    assists: int
    points: int
    shots: int
    # Only from the games the player chose to share; None = nothing shared.
    avg_self_rating: float | None
    work_on: list[GameWorkOn] | None
    # Team games already played, the player was in, still without a report.
    missing_reports: int


class TeamStatsRead(BaseModel):
    """GET /teams/{id}/stats -- for the captain: each member's numbers from
    their own reports on this team's games (2026-10-08). `scope` "season"
    sums the season, "last_game" shows the latest played team game only."""

    scope: str
    season_label: str
    last_game_date: date | None
    players: list[TeamPlayerStats]


class TeamStatsReminderRead(BaseModel):
    reminded: int
