from datetime import datetime

from app.models.exercise import TargetStat
from app.models.progress import StatHistory, UserStat

GRACE_PERIOD_DAYS = 10
# On-ice stats decay slower: on-ice ice time is scarce/scheduled (rinks,
# team practice) compared to off-ice training, so a 10-day gap between
# sessions is normal rather than a sign of detraining.
ON_ICE_GRACE_PERIOD_DAYS = 18

GRACE_PERIOD_DAYS_BY_STAT: dict[TargetStat, int] = {
    TargetStat.STRENGTH: GRACE_PERIOD_DAYS,
    TargetStat.AGILITY: GRACE_PERIOD_DAYS,
    TargetStat.ENDURANCE: GRACE_PERIOD_DAYS,
    TargetStat.INTELLECT: GRACE_PERIOD_DAYS,
    TargetStat.ON_ICE_SKATING: ON_ICE_GRACE_PERIOD_DAYS,
    TargetStat.PUCK_HANDLING: ON_ICE_GRACE_PERIOD_DAYS,
}

DECAY_RATE_PER_WEEK = 0.98
FLOOR_RATIO = 0.10


def get_grace_period_days(stat_type: TargetStat) -> int:
    return GRACE_PERIOD_DAYS_BY_STAT[stat_type]


def get_idle_days(stat: UserStat, now: datetime) -> float:
    # now must be tz-aware (e.g. datetime.now(timezone.utc)) to match
    # last_updated_at, which is stored tz-aware.
    return (now - stat.last_updated_at).total_seconds() / 86400


def is_decay_active(idle_days: float, stat_type: TargetStat) -> bool:
    return idle_days > get_grace_period_days(stat_type)


def get_effective_value(stat: UserStat, now: datetime) -> float:
    idle_days = get_idle_days(stat, now)
    if not is_decay_active(idle_days, stat.stat_type):
        return stat.current_value

    grace_period_days = get_grace_period_days(stat.stat_type)
    decay_weeks = (idle_days - grace_period_days) / 7
    effective = stat.current_value * (DECAY_RATE_PER_WEEK**decay_weeks)
    floor = stat.current_value * FLOOR_RATIO
    return max(effective, floor)


def get_stat_value_at_from_history(
    stat_type: TargetStat, history: list[StatHistory], at: datetime
) -> float:
    """Reconstructed value of a stat at an arbitrary past instant, from its
    real StatHistory rows (ascending by recorded_at, e.g.
    ProgressRepository.list_stat_history's order) -- same on-the-fly
    approximation SkillService uses for skill-value history: the most
    recent row at or before `at` is treated as a fresh (undecayed) UserStat
    as of its own recorded_at, then decayed forward to `at`. 0.0 if there's
    no history yet at that point (matches how a missing UserStat is treated
    elsewhere, e.g. SkillService._compute_breakdown).
    """
    latest: StatHistory | None = None
    for entry in history:
        if entry.recorded_at > at:
            break
        latest = entry
    if latest is None:
        return 0.0
    pseudo_stat = UserStat(
        stat_type=stat_type, current_value=latest.value, last_updated_at=latest.recorded_at
    )
    return get_effective_value(pseudo_stat, at)
