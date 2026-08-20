"""Stage 2.4 (2026-08-20 planning session): ScheduleService._pick_main's
role order (explosive/skill -> lower-body strength -> upper-body strength
-> accessories) and the unilateral tie-break within the lower-body role.
See test_pick_main_day_archetype.py for day-archetype rotation itself and
test_pick_main_muscle_balance.py for role 4's muscle-awareness.
"""
import uuid

import pytest

from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    MovementPattern,
    TrainingPhase,
)
from app.models.schedule import BlockPhase
from app.models.user import User
from app.services.schedule_service import ScheduleService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"roles_{unique}",
        email=f"roles_{unique}@example.com",
        password_hash="irrelevant",
        level=15,
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_exercise(name: str, pattern: MovementPattern, **fields) -> tuple[Exercise, ExerciseMovementPattern]:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        **fields,
    )
    return exercise, ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=pattern)


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


@pytest.mark.asyncio
async def test_role_order_is_explosive_then_lower_then_upper_then_accessories(db_session) -> None:
    """One candidate per role, count high enough to fit all four --
    the picked order must follow the fixed role sequence regardless of
    each exercise's alphabetical name, unlike every other axis in this
    system which the deterministic-random fixtures elsewhere rely on."""
    user = _make_user()
    db_session.add(user)
    pairs = [
        _make_exercise("Z-explosive", MovementPattern.STICK_HANDLING),
        _make_exercise("Z-lower", MovementPattern.SQUAT),
        _make_exercise("Z-upper", MovementPattern.PUSH),
        _make_exercise("Z-accessory", MovementPattern.CORE),
    ]
    db_session.add_all([e for e, _ in pairs] + [p for _, p in pairs])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [e for e, _ in pairs])
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["Z-explosive", "Z-lower", "Z-upper", "Z-accessory"]


@pytest.mark.asyncio
async def test_explosive_role_picks_at_most_one_exercise(db_session) -> None:
    """LOCOMOTION and STICK_HANDLING both have candidates -- role 1 must
    only ever fill one slot, leaving the other pattern free for role 4 to
    pick up as an ordinary accessory."""
    user = _make_user()
    db_session.add(user)
    pairs = [
        _make_exercise("A-locomotion", MovementPattern.LOCOMOTION),
        _make_exercise("A-stick", MovementPattern.STICK_HANDLING),
    ]
    db_session.add_all([e for e, _ in pairs] + [p for _, p in pairs])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [e for e, _ in pairs])
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    # Both patterns are eligible for role 1, but only one is picked there;
    # role 4 later picks up the other one -- both end up in the session,
    # just not both counted as the single "explosive" slot.
    assert len(picked) == 2
    assert {e.name for e in picked} == {"A-locomotion", "A-stick"}


@pytest.mark.asyncio
async def test_lower_body_role_prefers_unilateral_when_available(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    pairs = [
        _make_exercise("A-bilateral-squat", MovementPattern.SQUAT, is_unilateral=False),
        _make_exercise("B-unilateral-squat", MovementPattern.SQUAT, is_unilateral=True),
    ]
    db_session.add_all([e for e, _ in pairs] + [p for _, p in pairs])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [e for e, _ in pairs])
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["B-unilateral-squat"]


@pytest.mark.asyncio
async def test_lower_body_role_falls_back_to_bilateral_when_no_unilateral_candidate(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    exercise, pattern = _make_exercise(
        "Only-bilateral-squat", MovementPattern.SQUAT, is_unilateral=False
    )
    db_session.add_all([exercise, pattern])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [exercise])
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["Only-bilateral-squat"]


@pytest.mark.asyncio
async def test_upper_body_role_has_no_unilateral_preference(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unilateral tie-break is a lower-body (squat/hip_hinge) thing
    only -- a push/pull candidate marked is_unilateral=False must not be
    skipped in favor of one marked True. random.choice is pinned to
    alphabetically-*last*, deliberately picking the bilateral one by name
    -- if role 3 wrongly applied the same unilateral filter role 2 does,
    that would force the unilateral one regardless of this patch."""
    monkeypatch.setattr("random.choice", lambda pool: sorted(pool, key=lambda e: e.name)[-1])
    user = _make_user()
    db_session.add(user)
    pairs = [
        _make_exercise("A-unilateral-push", MovementPattern.PUSH, is_unilateral=True),
        _make_exercise("B-bilateral-push", MovementPattern.PUSH, is_unilateral=False),
    ]
    db_session.add_all([e for e, _ in pairs] + [p for _, p in pairs])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [e for e, _ in pairs])
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["B-bilateral-push"]
