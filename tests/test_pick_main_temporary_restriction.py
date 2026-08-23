"""End-to-end: a UserTemporaryRestriction actually keeps its movement
pattern out of a real generated session (P3 item #7) -- the user-facing
guarantee on top of test_exercise_repository_temporary_restriction.py's
unit-level coverage of the underlying list_for_assembly filter.

Runs against the same shared dev DB (real seeded catalog) as
test_pick_main_movement_pattern_axis.py -- unlike that file, this one does
NOT mock list_for_assembly, since that's exactly the code path being
verified here.
"""
import uuid
from datetime import date, timedelta

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import ExerciseCategory, MovementPattern
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.repositories.exercise_repository import ExerciseRepository
from app.services.schedule_service import ScheduleService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"restrictmain_{unique}",
        email=f"restrictmain_{unique}@example.com",
        password_hash="irrelevant",
        level=15,
    )


@pytest.mark.asyncio
async def test_restricted_pattern_never_appears_in_a_real_off_ice_main_block(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    db_session.add(
        UserTemporaryRestriction(
            user_id=user.id,
            movement_pattern=MovementPattern.SQUAT,
            expires_at=date.today() + timedelta(days=14),
        )
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    main_exercises = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    exercises = ExerciseRepository(db_session)
    patterns_by_exercise = await exercises.list_movement_patterns_by_exercise(
        [e.id for e in main_exercises]
    )
    all_patterns = {
        pattern for patterns in patterns_by_exercise.values() for pattern in patterns
    }
    assert MovementPattern.SQUAT not in all_patterns
