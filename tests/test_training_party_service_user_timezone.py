"""2026-09-18 fix (audit round 2 item #3): TrainingPartyService.create_party/
list_incoming_invites/_effective_status used date.today() (the server's
timezone) -- see ProgressService.get_streak's matching fix and
test_streak_consumer_day_plan.py's own cross-timezone test for the
established pattern this file follows.
"""
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from app.models.training_party import TrainingParty, TrainingPartyStatus
from app.models.user import User
from app.schemas.training_party import TrainingPartyCreate
from app.services.training_party_service import TrainingPartyService

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
async def test_create_party_rejects_the_servers_today_as_already_past_locally(
    db_session, monkeypatch
) -> None:
    """target_date is the server's UTC today -- one calendar day *before*
    this user's own local today (Pacific/Kiritimati, UTC+14). The server's
    date.today() check would still accept it (>= today); the user's own
    local today has already moved past it, so it must be rejected as a
    past date. The date guard runs before friend validation, so an
    unrelated random friend_id never gets reached."""
    monkeypatch.setattr("app.services.training_party_service.datetime", _FixedInstant)
    creator = _make_user()
    db_session.add(creator)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await TrainingPartyService(db_session).create_party(
            creator, TrainingPartyCreate(target_date=UTC_TODAY, friend_ids=[uuid.uuid4()])
        )

    assert exc_info.value.status_code == 400


def test_effective_status_expires_a_pending_party_by_the_viewers_local_today(monkeypatch) -> None:
    """Pure unit test, no DB -- target_date is the server's UTC today,
    already the viewer's local yesterday (Pacific/Kiritimati, UTC+14).
    _effective_status has no single "owning" timezone (a party can span
    several members), so it judges "expired" from the specific viewer
    asking, not the creator's or some fixed server notion of today."""
    monkeypatch.setattr("app.services.training_party_service.datetime", _FixedInstant)
    viewer = _make_user()
    party = TrainingParty(
        id=uuid.uuid4(), created_by=viewer.id, target_date=UTC_TODAY,
        status=TrainingPartyStatus.PENDING,
    )

    result = TrainingPartyService._effective_status(party, viewer)

    assert result == "expired"
