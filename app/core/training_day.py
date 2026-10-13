"""A training is done on its own day (2026-10-10, owner's call): the
next days can be looked at, not started -- a session ticked off ahead of
time would credit stats, the streak and the block's progress for work
that hasn't happened."""
from datetime import date, datetime, timedelta, timezone
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


# Б2 (2026-10-13): the offline queue sends when the phone is back online,
# so a write carries when the set was really done. Trusted only within
# reason -- a phone clock a bit ahead, a queue at most two days old;
# anything else is server time.
PERFORMED_AT_FUTURE_SLACK = timedelta(minutes=5)
PERFORMED_AT_MAX_AGE = timedelta(hours=48)


def effective_performed_at(performed_at: datetime | None, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if performed_at is None:
        return now
    if performed_at.tzinfo is None:
        performed_at = performed_at.replace(tzinfo=timezone.utc)
    if performed_at > now + PERFORMED_AT_FUTURE_SLACK or performed_at < now - PERFORMED_AT_MAX_AGE:
        return now
    return min(performed_at, now)


def local_date(moment: datetime, user: User) -> date:
    """The player's calendar day a moment falls on -- what the streak counts."""
    try:
        return moment.astimezone(ZoneInfo(user.timezone or "UTC")).date()
    except Exception:
        return moment.astimezone(timezone.utc).date()
