"""2026-09-18 fix (audit round 2 item #3): ExerciseRepository.
list_active_restricted_patterns/list_active_restricted_muscle_groups used
date.today() (the server's timezone) for the expires_at >= today check --
see ProgressService.get_streak's matching fix and
test_streak_consumer_day_plan.py's own cross-timezone test for the
established pattern this file follows. Same fixture shape as
test_exercise_repository_temporary_restriction.py's own
test_expired_restriction_excludes_nothing.
"""
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.models.exercise import Exercise, ExerciseCategory, ExerciseMovementPattern, MovementPattern, TrainingPhase
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.repositories.exercise_repository import ExerciseRepository

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


def _make_exercise(**overrides) -> Exercise:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(), name=f"Exercise {unique}", category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN, difficulty_level=1,
    )
    defaults.update(overrides)
    return Exercise(**defaults)


@pytest.mark.asyncio
async def test_restriction_expiring_on_the_servers_today_is_already_expired_locally(
    db_session, monkeypatch
) -> None:
    """expires_at is stamped at the server's UTC today -- one calendar day
    *before* this user's own local today (Pacific/Kiritimati, UTC+14). The
    server's date.today() would still see it as >= today (still active,
    still excluding the exercise); the user's own local today has already
    moved past it, so the exercise must be back in the assembly pool."""
    monkeypatch.setattr("app.repositories.exercise_repository.datetime", _FixedInstant)
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([
        user,
        exercise,
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT),
        UserTemporaryRestriction(
            id=uuid.uuid4(), user_id=user.id, movement_pattern=MovementPattern.SQUAT,
            expires_at=UTC_TODAY,
        ),
    ])
    await db_session.flush()

    result = await ExerciseRepository(db_session).list_for_assembly(
        phase=TrainingPhase.MAIN, user=user, category=ExerciseCategory.OFF_ICE
    )

    assert exercise.id in {e.id for e in result}
