"""2026-09-18 fix (audit round 2 item #3): UserTemporaryRestrictionService.
list_active/list_resolved/report used date.today() (the server's timezone)
-- see ProgressService.get_streak's matching fix and
test_streak_consumer_day_plan.py's own cross-timezone test for the
established pattern this file follows.
"""
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.models.exercise import MovementPattern
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.services.user_temporary_restriction_service import UserTemporaryRestrictionService

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
async def test_list_active_treats_the_users_local_today_as_the_expiry_boundary(
    db_session, monkeypatch
) -> None:
    """expires_at is stamped at the server's UTC today -- one calendar day
    *before* this user's own local today (Pacific/Kiritimati, UTC+14). The
    server's date.today() would still see it as >= today (active); the
    user's own local today has already moved past it (expired)."""
    monkeypatch.setattr("app.services.user_temporary_restriction_service.datetime", _FixedInstant)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserTemporaryRestriction(
            id=uuid.uuid4(),
            user_id=user.id,
            movement_pattern=MovementPattern.ROTATION,
            expires_at=UTC_TODAY,
        )
    )
    await db_session.flush()

    active = await UserTemporaryRestrictionService(db_session).list_active(user)

    assert active == []


@pytest.mark.asyncio
async def test_report_sets_expires_at_from_the_users_local_today(db_session, monkeypatch) -> None:
    monkeypatch.setattr("app.services.user_temporary_restriction_service.datetime", _FixedInstant)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    from datetime import timedelta

    from app.services.user_temporary_restriction_service import DEFAULT_RESTRICTION_DAYS

    restriction = await UserTemporaryRestrictionService(db_session).report(
        user, MovementPattern.ROTATION, None, "test"
    )

    assert restriction.expires_at == LOCAL_TODAY + timedelta(days=DEFAULT_RESTRICTION_DAYS)
