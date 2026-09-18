"""2026-09-18 fix (audit round 2 item #3, continuation of round 1 item #10):
ScheduleService.get_current_weekly_plan/_patch_weekly_plan/_pick_main used
date.today() (the server's timezone) to decide "today", not the user's own
-- see ProgressService.get_streak's matching fix and
test_streak_consumer_day_plan.py's test_streak_stamped_with_the_users_local_date_not_the_servers
for the established pattern this file follows: a real UTC instant that
genuinely straddles two different calendar dates in Pacific/Kiritimati
(UTC+14) vs. UTC itself, deterministic and large rather than relying on the
suite happening to run near a real midnight boundary.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.models.schedule import WeeklyPlan
from app.models.user import User
from app.services.schedule_service import ScheduleService

FIXED_UTC_INSTANT = datetime(2026, 3, 10, 23, 30, tzinfo=timezone.utc)
LOCAL_TODAY = FIXED_UTC_INSTANT.astimezone(ZoneInfo("Pacific/Kiritimati")).date()
UTC_TODAY = FIXED_UTC_INSTANT.date()
assert LOCAL_TODAY != UTC_TODAY  # sanity: this instant genuinely straddles the two dates


class _FixedInstant(datetime):
    @classmethod
    def now(cls, tz=None) -> datetime:
        return FIXED_UTC_INSTANT if tz is None else FIXED_UTC_INSTANT.astimezone(tz)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"tz_{unique}",
        email=f"tz_{unique}@example.com",
        password_hash="irrelevant",
        timezone="Pacific/Kiritimati",
    )


@pytest.mark.asyncio
async def test_get_current_weekly_plan_uses_the_users_local_date(db_session, monkeypatch) -> None:
    """A WeeklyPlan whose week_start_date is LOCAL_TODAY -- the server's
    UTC "today" is still the day before, so the pre-fix date.today() would
    consider this week not-yet-current and 404. week_start_date <= today
    is exactly the boundary get_current checks."""
    monkeypatch.setattr("app.services.schedule_service.datetime", _FixedInstant)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=LOCAL_TODAY, day_plans=[])
    )
    await db_session.flush()

    result = await ScheduleService(db_session).get_current_weekly_plan(user)

    assert result.week_start_date == LOCAL_TODAY


@pytest.mark.asyncio
async def test_patch_current_weekly_plan_uses_the_users_local_date(db_session, monkeypatch) -> None:
    """Same boundary, exercised through _patch_weekly_plan's own
    get_current call (week_start_date=None path) rather than
    get_current_weekly_plan's."""
    from app.schemas.schedule import DayPlanIn, WeeklyPlanPatch
    from app.models.schedule import DayPlan, DaySessionType

    monkeypatch.setattr("app.services.schedule_service.datetime", _FixedInstant)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        WeeklyPlan(
            id=uuid.uuid4(),
            user_id=user.id,
            week_start_date=LOCAL_TODAY,
            day_plans=[
                DayPlan(id=uuid.uuid4(), date=LOCAL_TODAY, session_type=DaySessionType.REST)
            ],
        )
    )
    await db_session.flush()

    result = await ScheduleService(db_session).patch_current_weekly_plan(
        user, WeeklyPlanPatch(days=[DayPlanIn(date=LOCAL_TODAY, session_type=DaySessionType.REST)])
    )

    assert result.conflicts == []
    assert result.weekly_plan.week_start_date == LOCAL_TODAY
