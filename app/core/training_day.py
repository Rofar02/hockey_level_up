"""A training is done on its own day (2026-10-10, owner's call): the
next days can be looked at, not started -- a session ticked off ahead of
time would credit stats, the streak and the block's progress for work
that hasn't happened."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status

from app.models.user import User

NOT_YET_DETAIL = "Эту тренировку можно начать в её день"


def user_today(user: User) -> date:
    try:
        return datetime.now(ZoneInfo(user.timezone or "UTC")).date()
    except Exception:
        return datetime.now(timezone.utc).date()


def require_day_started(day: date, user: User) -> None:
    """409 for a day still ahead in the player's own time zone."""
    if day > user_today(user):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NOT_YET_DETAIL)
