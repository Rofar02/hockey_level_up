"""2026-09-20 fix (round-4 audit): DELOAD's own MAIN_EXERCISE_COUNT_RANGE
minimum (3) is smaller than role 1 (<=1) + role 2 (<=2, squat + hip_hinge)
+ role 3 (<=2, push + pull) = <=5 slots together. Before this fix, a
DELOAD session where role 1 (explosive/skill) won its optional slot AND
`count` resolved to the minimum (3) left ZERO budget for role 3 --
neither PUSH nor PULL made it into the session at all, contradicting
ScheduleService._pick_main's own "role 2/3 picking one SQUAT/HIP_HINGE
and one PUSH/PULL each is already a natural push/pull balance" framing.
Role 1 now yields (is skipped outright) below _MIN_COUNT_TO_ATTEMPT_ROLE1.
"""
import uuid
from datetime import date

import pytest

from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    MovementPattern,
    TrainingPhase,
)
from app.models.schedule import BlockPhase, TrainingBlock
from app.models.user import User
from app.services import schedule_service
from app.services.schedule_service import ScheduleService

TODAY = date(2026, 8, 20)


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(), username=f"budget_{unique}", email=f"budget_{unique}@example.com",
        password_hash="irrelevant", level=15,
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_exercise(name: str, pattern: MovementPattern) -> tuple[Exercise, ExerciseMovementPattern]:
    exercise = Exercise(
        id=uuid.uuid4(), name=name, category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN, difficulty_level=1,
    )
    return exercise, ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=pattern)


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


@pytest.mark.asyncio
async def test_deload_minimum_count_still_leaves_room_for_upper_body(
    db_session, monkeypatch
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    locomotion_ex, locomotion_pattern = _make_exercise("Locomotion-drill", MovementPattern.LOCOMOTION)
    squat_ex, squat_pattern = _make_exercise("Squat-ex", MovementPattern.SQUAT)
    hip_hinge_ex, hip_hinge_pattern = _make_exercise("HipHinge-ex", MovementPattern.HIP_HINGE)
    push_ex, push_pattern = _make_exercise("Push-ex", MovementPattern.PUSH)
    pull_ex, pull_pattern = _make_exercise("Pull-ex", MovementPattern.PULL)
    db_session.add_all([
        locomotion_ex, squat_ex, hip_hinge_ex, push_ex, pull_ex,
        locomotion_pattern, squat_pattern, hip_hinge_pattern, push_pattern, pull_pattern,
    ])
    block = TrainingBlock(user_id=user.id, block_number=1, phase=BlockPhase.DELOAD)
    db_session.add(block)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [locomotion_ex, squat_ex, hip_hinge_ex, push_ex, pull_ex])

    # Force count to DELOAD's minimum (3), same worst case the bug report
    # reproduced.
    monkeypatch.setattr(schedule_service.random, "randint", lambda lo, hi: lo)

    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.DELOAD, training_block=block, today=TODAY
    )
    picked_names = {e.name for e in picked}

    assert len(picked) == 3
    # Role 1 (explosive) yields at this count -- no locomotion pick.
    assert "Locomotion-drill" not in picked_names
    # Role 2 (lower body) fills both of its own slots as before.
    assert "Squat-ex" in picked_names and "HipHinge-ex" in picked_names
    # Role 3 (upper body) now gets the remaining slot -- at least one of
    # PUSH/PULL, never zero.
    assert "Push-ex" in picked_names or "Pull-ex" in picked_names


@pytest.mark.asyncio
async def test_role1_still_fires_at_a_normal_count(db_session, monkeypatch) -> None:
    """Sanity check: the round-4 fix only touches the tightest DELOAD
    count -- accumulation's own (5, 6) range must still let role 1 pick
    normally."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    locomotion_ex, locomotion_pattern = _make_exercise("Locomotion-drill", MovementPattern.LOCOMOTION)
    squat_ex, squat_pattern = _make_exercise("Squat-ex", MovementPattern.SQUAT)
    hip_hinge_ex, hip_hinge_pattern = _make_exercise("HipHinge-ex", MovementPattern.HIP_HINGE)
    push_ex, push_pattern = _make_exercise("Push-ex", MovementPattern.PUSH)
    pull_ex, pull_pattern = _make_exercise("Pull-ex", MovementPattern.PULL)
    db_session.add_all([
        locomotion_ex, squat_ex, hip_hinge_ex, push_ex, pull_ex,
        locomotion_pattern, squat_pattern, hip_hinge_pattern, push_pattern, pull_pattern,
    ])
    block = TrainingBlock(user_id=user.id, block_number=1, phase=BlockPhase.ACCUMULATION)
    db_session.add(block)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [locomotion_ex, squat_ex, hip_hinge_ex, push_ex, pull_ex])
    monkeypatch.setattr(schedule_service.random, "randint", lambda lo, hi: hi)

    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
    )
    picked_names = {e.name for e in picked}

    assert "Locomotion-drill" in picked_names
    assert "Squat-ex" in picked_names and "HipHinge-ex" in picked_names
    assert "Push-ex" in picked_names and "Pull-ex" in picked_names
