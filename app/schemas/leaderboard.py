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
    rank: int
    rating_excess: float
