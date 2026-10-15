import uuid

from pydantic import BaseModel

from app.models.user import Position


class LeaderboardEntryRead(BaseModel):
    id: uuid.UUID
    last_name: str
    first_name: str
    patronymic: str | None = None
    avatar_url: str | None = None
    position: Position | None = None
    jersey_number: int | None = None
    rating_excess: float


class LeaderboardMeRead(BaseModel):
    # Both null for a player not in the rating yet (no birth date) -- only
    # with `optional=1`, see get_my_leaderboard_position (15.10).
    rank: int | None
    rating_excess: float | None
    # What to do to get in, shown instead of the rank.
    hint: str | None = None
