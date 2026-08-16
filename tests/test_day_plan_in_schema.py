"""DayPlanIn.on_ice_minutes -- pure schema validation, no DB needed. Phase 6:
ON_ICE states its rink-time budget explicitly; every other session_type must
leave it unset (see app.schemas.schedule.DayPlanIn).
"""
from datetime import date

import pytest
from pydantic import ValidationError

from app.models.schedule import DaySessionType
from app.schemas.schedule import DayPlanIn


def test_on_ice_minutes_accepted_for_on_ice() -> None:
    day = DayPlanIn(date=date.today(), session_type=DaySessionType.ON_ICE, on_ice_minutes=60)
    assert day.on_ice_minutes == 60


def test_on_ice_minutes_defaults_to_none() -> None:
    day = DayPlanIn(date=date.today(), session_type=DaySessionType.OFF_ICE)
    assert day.on_ice_minutes is None


def test_on_ice_minutes_rejected_for_non_on_ice_session_type() -> None:
    with pytest.raises(ValidationError):
        DayPlanIn(date=date.today(), session_type=DaySessionType.OFF_ICE, on_ice_minutes=60)


def test_on_ice_minutes_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        DayPlanIn(date=date.today(), session_type=DaySessionType.ON_ICE, on_ice_minutes=0)
