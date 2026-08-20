"""Body-muscles map (2026-08-20 planning session): app.core.muscle_load's
pure grace-period-then-half-life decay. Pure unit tests -- get_idle_hours/
is_decay_active/get_effective_muscle_load only take a UserMuscleLoad
instance and a `now`, no DB needed, same shape as test_stat_decay.py.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.core.muscle_load import (
    GRACE_PERIOD_HOURS,
    HALF_LIFE_HOURS,
    get_effective_muscle_load,
    get_idle_hours,
    is_decay_active,
)
from app.models.exercise import MuscleGroup
from app.models.progress import UserMuscleLoad

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def _load(idle_hours: float, current_value: float = 8.0) -> UserMuscleLoad:
    return UserMuscleLoad(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        muscle_group=MuscleGroup.QUADS,
        current_value=current_value,
        last_updated_at=NOW - timedelta(hours=idle_hours),
    )


def test_stays_at_peak_within_the_grace_period() -> None:
    load = _load(idle_hours=GRACE_PERIOD_HOURS - 0.01, current_value=8.0)
    assert is_decay_active(GRACE_PERIOD_HOURS - 0.01) is False
    assert get_effective_muscle_load(load, NOW) == 8.0


def test_decay_starts_right_past_the_grace_period() -> None:
    assert is_decay_active(GRACE_PERIOD_HOURS + 0.01) is True


def test_halves_after_one_half_life_past_grace() -> None:
    load = _load(idle_hours=GRACE_PERIOD_HOURS + HALF_LIFE_HOURS, current_value=8.0)
    effective = get_effective_muscle_load(load, NOW)
    assert abs(effective - 4.0) < 1e-9


def test_quarters_after_two_half_lives_past_grace() -> None:
    load = _load(idle_hours=GRACE_PERIOD_HOURS + 2 * HALF_LIFE_HOURS, current_value=8.0)
    effective = get_effective_muscle_load(load, NOW)
    assert abs(effective - 2.0) < 1e-9


def test_approaches_zero_with_no_explicit_floor() -> None:
    # Unlike stat decay's 10%-of-peak floor, muscle load has none -- full
    # recovery to (near) zero is the expected outcome, not a loss.
    load = _load(idle_hours=GRACE_PERIOD_HOURS + 10 * HALF_LIFE_HOURS, current_value=8.0)
    effective = get_effective_muscle_load(load, NOW)
    assert 0.0 < effective < 0.01


def test_get_idle_hours_matches_the_constructed_gap() -> None:
    load = _load(idle_hours=36.0)
    assert abs(get_idle_hours(load, NOW) - 36.0) < 1e-9
