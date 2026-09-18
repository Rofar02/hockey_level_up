"""2026-09-18 fix (audit round 2 item #3): TrainingBlockService.
resolve_active_block/get_or_create_and_resolve used date.today() (the
server's timezone) to resolve "today" when no explicit value was injected --
see ProgressService.get_streak's matching fix and
test_streak_consumer_day_plan.py's own cross-timezone test for the
established pattern this file follows.
"""
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.models.user import User
from app.services.training_block_service import TrainingBlockService

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
async def test_get_or_create_and_resolve_stamps_the_users_local_date(db_session, monkeypatch) -> None:
    """No `today` injected, no existing TrainingBlock -- the fresh block's
    phase_started_at must be the user's own local today, not the server's
    (UTC) one."""
    monkeypatch.setattr("app.services.training_block_service.datetime", _FixedInstant)
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    block = await TrainingBlockService(db_session).get_or_create_and_resolve(user.id)

    assert block.phase_started_at == LOCAL_TODAY
    assert block.phase_started_at != UTC_TODAY
