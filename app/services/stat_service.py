from datetime import datetime

from app.models.progress import UserStat

GRACE_PERIOD_DAYS = 10
DECAY_RATE_PER_WEEK = 0.98
FLOOR_RATIO = 0.10


def get_idle_days(stat: UserStat, now: datetime) -> float:
    # now must be tz-aware (e.g. datetime.now(timezone.utc)) to match
    # last_updated_at, which is stored tz-aware.
    return (now - stat.last_updated_at).total_seconds() / 86400


def is_decay_active(idle_days: float) -> bool:
    return idle_days > GRACE_PERIOD_DAYS


def get_effective_value(stat: UserStat, now: datetime) -> float:
    idle_days = get_idle_days(stat, now)
    if not is_decay_active(idle_days):
        return stat.current_value

    decay_weeks = (idle_days - GRACE_PERIOD_DAYS) / 7
    effective = stat.current_value * (DECAY_RATE_PER_WEEK**decay_weeks)
    floor = stat.current_value * FLOOR_RATIO
    return max(effective, floor)
