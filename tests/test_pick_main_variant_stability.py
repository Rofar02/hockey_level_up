"""Phase: П.3 variant rotation in ScheduleService._pick_main.

A UserMovementPatternVariant pin holds the same exercise stable within one
TrainingBlock, rotates to a different exercise at the boundary of a new
(non-macrocycle-deload) block, and holds through a macrocycle-deload
block's boundary instead (see _pick_main's docstring for the full
rationale). All scenarios here seed candidates for exactly one
movement_pattern (SQUAT) so the pool/pin interaction is unambiguous --
`random.shuffle` is patched to a no-op and `random.choice` to
alphabetically-first, same style as test_schedule_service_pick_main.py,
so any pick that ISN'T explained by the pin is deterministic and
distinguishable from one that is.
"""
import random
import uuid

import pytest
from sqlalchemy import select

from app.models.exercise import (
    EquipmentType,
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    MovementPattern,
    TrainingPhase,
    UserMovementPatternVariant,
)
from app.models.schedule import BlockPhase, TrainingBlock
from app.models.user import User
from app.services.schedule_service import ScheduleService


@pytest.fixture(autouse=True)
def deterministic_random(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(random, "randint", lambda a, b: 3)
    monkeypatch.setattr(random, "choice", lambda pool: sorted(pool, key=lambda e: e.name)[0])
    monkeypatch.setattr(random, "shuffle", lambda seq: None)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"variant_{unique}",
        email=f"variant_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        level=15,
    )


def _make_exercise(name: str) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        equipment_type=EquipmentType.BODYWEIGHT,
    )


def _make_block(user: User, *, block_number: int, is_macrocycle_deload: bool = False) -> TrainingBlock:
    return TrainingBlock(
        user_id=user.id,
        block_number=block_number,
        phase=BlockPhase.ACCUMULATION,
        is_macrocycle_deload=is_macrocycle_deload,
    )


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, equipment_access, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


async def _get_pin(db_session, user: User) -> UserMovementPatternVariant:
    result = await db_session.execute(
        select(UserMovementPatternVariant).where(
            UserMovementPatternVariant.user_id == user.id,
            UserMovementPatternVariant.category == ExerciseCategory.OFF_ICE,
            UserMovementPatternVariant.movement_pattern == MovementPattern.SQUAT,
        )
    )
    return result.scalar_one()


async def _seed_two_squat_candidates(db_session) -> tuple[Exercise, Exercise]:
    a, b = _make_exercise("A-squat"), _make_exercise("B-squat")
    db_session.add_all([a, b])
    db_session.add_all([
        ExerciseMovementPattern(exercise_id=a.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=b.id, movement_pattern=MovementPattern.SQUAT),
    ])
    await db_session.flush()
    return a, b


@pytest.mark.asyncio
async def test_first_pick_creates_a_pin(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    a, b = await _seed_two_squat_candidates(db_session)
    block = _make_block(user, block_number=1)
    db_session.add(block)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [a, b])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block
    )

    assert [e.name for e in picked] == ["A-squat"]
    pin = await _get_pin(db_session, user)
    assert pin.exercise_id == a.id
    assert pin.block_number == 1


@pytest.mark.asyncio
async def test_same_block_keeps_the_pinned_exercise(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even with random.choice re-patched to favor a different exercise,
    a second call within the same block must still return the pin."""
    user = _make_user()
    db_session.add(user)
    a, b = await _seed_two_squat_candidates(db_session)
    block = _make_block(user, block_number=1)
    db_session.add(block)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [a, b])
    first = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block
    )
    assert [e.name for e in first] == ["A-squat"]

    # Bias choice toward B -- if the pin weren't actually being used, this
    # would flip the result.
    monkeypatch.setattr(random, "choice", lambda pool: sorted(pool, key=lambda e: e.name)[-1])
    second = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block
    )

    assert [e.name for e in second] == ["A-squat"]


@pytest.mark.asyncio
async def test_normal_block_boundary_forces_a_different_variant(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    a, b = await _seed_two_squat_candidates(db_session)
    block1 = _make_block(user, block_number=1)
    db_session.add(block1)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [a, b])
    await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block1
    )

    # block_number=2 -- not a macrocycle-deload block (interval=4).
    block2 = _make_block(user, block_number=2)
    db_session.add(block2)
    await db_session.flush()
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block2
    )

    # A was excluded from the pool at the rotation boundary -- B is the
    # only remaining candidate, not a coincidence of alphabetical order.
    assert [e.name for e in picked] == ["B-squat"]
    pin = await _get_pin(db_session, user)
    assert pin.exercise_id == b.id
    assert pin.block_number == 2


@pytest.mark.asyncio
async def test_macrocycle_deload_boundary_holds_the_variant(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    a, b = await _seed_two_squat_candidates(db_session)
    block1 = _make_block(user, block_number=1)
    db_session.add(block1)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [a, b])
    await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block1
    )

    # block_number=4 -- a macrocycle-deload block (4 % 4 == 0).
    block4 = _make_block(user, block_number=4, is_macrocycle_deload=True)
    db_session.add(block4)
    await db_session.flush()
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block4
    )

    # Held, not rotated -- still A, even though a boundary was crossed.
    assert [e.name for e in picked] == ["A-squat"]
    pin = await _get_pin(db_session, user)
    assert pin.exercise_id == a.id
    assert pin.block_number == 4  # bookmark bumped even though exercise_id didn't change


@pytest.mark.asyncio
async def test_rotation_resumes_after_the_macrocycle_deload_block(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    a, b = await _seed_two_squat_candidates(db_session)
    block1 = _make_block(user, block_number=1)
    db_session.add(block1)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [a, b])
    await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block1
    )

    block4 = _make_block(user, block_number=4, is_macrocycle_deload=True)
    db_session.add(block4)
    await db_session.flush()
    await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block4
    )
    # Still A, held through the deload block (see previous test).

    # block_number=5 -- back to a normal (non-deload) boundary.
    block5 = _make_block(user, block_number=5)
    db_session.add(block5)
    await db_session.flush()
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block5
    )

    assert [e.name for e in picked] == ["B-squat"]
    pin = await _get_pin(db_session, user)
    assert pin.exercise_id == b.id
    assert pin.block_number == 5


@pytest.mark.asyncio
async def test_single_candidate_stays_stable_at_a_rotation_boundary(db_session) -> None:
    """No alternative exists for this pattern -- the exclusion-on-rotation
    rule must fall back to the unfiltered pool rather than emptying it."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    only = _make_exercise("Only-squat")
    db_session.add(only)
    db_session.add(ExerciseMovementPattern(exercise_id=only.id, movement_pattern=MovementPattern.SQUAT))
    block1 = _make_block(user, block_number=1)
    db_session.add(block1)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [only])
    await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block1
    )

    block2 = _make_block(user, block_number=2)
    db_session.add(block2)
    await db_session.flush()
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block2
    )

    assert [e.name for e in picked] == ["Only-squat"]
    pin = await _get_pin(db_session, user)
    assert pin.exercise_id == only.id
    assert pin.block_number == 2


@pytest.mark.asyncio
async def test_no_training_block_skips_stability_entirely(db_session) -> None:
    """Matches every pre-existing call site/test that never passes
    training_block -- no pin is read or written."""
    user = _make_user()
    db_session.add(user)
    a, b = await _seed_two_squat_candidates(db_session)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [a, b])
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["A-squat"]
    result = await db_session.execute(
        select(UserMovementPatternVariant).where(UserMovementPatternVariant.user_id == user.id)
    )
    assert result.scalar_one_or_none() is None
