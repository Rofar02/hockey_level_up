"""Per-stat decay grace period (stat_service.GRACE_PERIOD_DAYS_BY_STAT).

on_ice_skating/puck_handling get an 18-day grace period instead of the
existing 4 stats' 10 days -- on-ice ice time is scarcer/scheduled than
off-ice training, so a longer gap between sessions shouldn't read as
detraining. Pure unit tests: get_idle_days/is_decay_active/get_effective_value
only take a UserStat instance and a `now`, no DB needed.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.models.exercise import TargetStat
from app.models.progress import UserStat
from app.services.stat_service import (
    GRACE_PERIOD_DAYS,
    ON_ICE_GRACE_PERIOD_DAYS,
    get_effective_value,
    get_grace_period_days,
    is_decay_active,
)

NOW = datetime(2026, 8, 6, tzinfo=timezone.utc)

EXISTING_STATS = (
    TargetStat.STRENGTH,
    TargetStat.AGILITY,
    TargetStat.ENDURANCE,
    TargetStat.INTELLECT,
)
ON_ICE_STATS = (TargetStat.ON_ICE_SKATING, TargetStat.PUCK_HANDLING)


def _stat(stat_type: TargetStat, idle_days: float, current_value: float = 50.0) -> UserStat:
    return UserStat(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        stat_type=stat_type,
        current_value=current_value,
        last_updated_at=NOW - timedelta(days=idle_days),
    )


def test_existing_stats_keep_the_original_10_day_grace_period() -> None:
    for stat_type in EXISTING_STATS:
        assert get_grace_period_days(stat_type) == 10 == GRACE_PERIOD_DAYS


def test_on_ice_stats_get_an_18_day_grace_period() -> None:
    for stat_type in ON_ICE_STATS:
        assert get_grace_period_days(stat_type) == 18 == ON_ICE_GRACE_PERIOD_DAYS


def test_existing_stats_decay_past_10_days_but_on_ice_stats_do_not_yet() -> None:
    # 12 idle days: past the existing stats' grace period, still inside the
    # on-ice stats' longer one.
    for stat_type in EXISTING_STATS:
        assert is_decay_active(12, stat_type) is True
    for stat_type in ON_ICE_STATS:
        assert is_decay_active(12, stat_type) is False


def test_on_ice_stats_decay_past_18_days() -> None:
    for stat_type in ON_ICE_STATS:
        assert is_decay_active(19, stat_type) is True


def test_get_effective_value_respects_the_longer_on_ice_grace_period() -> None:
    # 15 idle days: an existing stat would already be decaying, but
    # on_ice_skating (18-day grace) hasn't started yet -- effective value
    # stays exactly at current_value.
    on_ice_stat = _stat(TargetStat.ON_ICE_SKATING, idle_days=15, current_value=60.0)
    assert get_effective_value(on_ice_stat, NOW) == 60.0

    strength_stat = _stat(TargetStat.STRENGTH, idle_days=15, current_value=60.0)
    assert get_effective_value(strength_stat, NOW) < 60.0


def test_get_effective_value_decays_on_ice_stat_once_past_18_days() -> None:
    on_ice_stat = _stat(TargetStat.PUCK_HANDLING, idle_days=25, current_value=60.0)
    effective = get_effective_value(on_ice_stat, NOW)
    assert effective < 60.0
    # decay_weeks = (25 - 18) / 7 = 1.0 week exactly
    assert effective == 60.0 * 0.98
