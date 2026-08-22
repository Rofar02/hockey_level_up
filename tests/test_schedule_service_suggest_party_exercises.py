"""ScheduleService.suggest_party_exercises: the co-op exercise-suggestion
engine behind TrainingPartyService.suggest_exercises. Equipment (Stage 2.2)
is has_gym_access (bypasses the filter entirely) plus a per-exercise
required-item set checked against each member's own owned-item set,
intersected across every member -- see that method's docstring for why this
can't just reuse list_for_assembly's single-user check -- and difficulty is
capped at the weakest member's ceiling, never relaxed.

Diversity is bucketed by movement_pattern, not target_stat (see
ScheduleService._pick_main's docstring for why) -- exercises below are
tagged with ExerciseMovementPattern, not ExerciseTargetStat.
"""
import uuid

import pytest

from app.models.exercise import (
    EquipmentItem,
    Exercise,
    ExerciseCategory,
    ExerciseEquipmentItem,
    ExerciseMovementPattern,
    MovementPattern,
    TrainingPhase,
    UserEquipmentItem,
)
from app.models.user import User
from app.services.schedule_service import ScheduleService

# _CLEAN_PATTERNS no longer buys real isolation on its own -- the 90-exercise
# import (see static/exercise_import_review.json) added real off_ice/MAIN
# exercises tagged with these too, so every test below now also stubs
# list_exercises via _isolate (see below) rather than relying on any pattern
# being untouched by the real catalog.
_CLEAN_PATTERNS = (MovementPattern.WRIST_MOBILITY, MovementPattern.SHOULDER_MOBILITY, MovementPattern.CORE)


def _isolate(service: ScheduleService, exercises: dict) -> None:
    """Make list_exercises return only this test's own exercises, filtered
    the same way suggest_party_exercises' real call
    (category=OFF_ICE, phase=MAIN) would -- the real dev DB now has a real
    seeded catalog that would otherwise leak into these tests' pools."""

    async def fake_list_exercises(*, category=None, phase=None, target_stat=None):
        pool = list(exercises.values())
        if category is not None:
            pool = [e for e in pool if e.category == category]
        if phase is not None:
            pool = [e for e in pool if e.phase == phase]
        return pool

    service._exercises.list_exercises = fake_list_exercises


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"suggest_{unique}",
        email=f"suggest_{unique}@example.com",
        password_hash="irrelevant",
        friend_code=unique.upper(),
        level=1,
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_exercise(**overrides) -> tuple:
    # movement_pattern/equipment_items aren't real Exercise fields (see
    # ExerciseMovementPattern/ExerciseEquipmentItem) -- popped here and
    # returned as companion rows the caller must also add to the session,
    # since suggest_party_exercises now buckets/matches on real m2m
    # queries, not in-memory attributes. Variable-length: (exercise,
    # movement_pattern_row, *equipment_rows) -- unpack with
    # `exercise, *rows = _make_exercise(...)`.
    movement_pattern = overrides.pop("movement_pattern", MovementPattern.SQUAT)
    equipment_items = overrides.pop("equipment_items", ())
    defaults = dict(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )
    defaults.update(overrides)
    exercise = Exercise(**defaults)
    equipment_rows = [
        ExerciseEquipmentItem(exercise_id=exercise.id, equipment_item=item) for item in equipment_items
    ]
    return (
        exercise,
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=movement_pattern),
        *equipment_rows,
    )


def _add(db_session, *items) -> None:
    """Add a mix of plain models, (Exercise, ExerciseMovementPattern) pairs, and
    lists of either to the session -- flattens pairs so callers can pass
    _make_exercise(...)'s return value directly alongside plain User rows."""
    flat: list = []
    for item in items:
        candidates = item if isinstance(item, list) else [item]
        for candidate in candidates:
            if isinstance(candidate, tuple):
                flat.extend(candidate)
            else:
                flat.append(candidate)
    db_session.add_all(flat)


@pytest.mark.asyncio
async def test_equipment_without_common_ground_excludes_gym_only_exercise(db_session) -> None:
    """A gym-only exercise is dropped once a bodyweight-only member is in the
    party, even though a gym member alone would see it -- the member without
    the equipment excludes it from the shared set. Both exercises share one
    (clean) movement_pattern so they compete in the same pattern pool --
    proves the exclusion is about equipment, not just "different pattern got
    picked"."""
    gym_user = _make_user(has_gym_access=True)
    bodyweight_user = _make_user()
    gym_only, *gym_only_rows = _make_exercise(
        equipment_items=[EquipmentItem.BARBELL], movement_pattern=_CLEAN_PATTERNS[0]
    )
    _add(db_session, gym_user, bodyweight_user, (gym_only, *gym_only_rows))
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate(service, {"gym_only": gym_only})
    suggested = await service.suggest_party_exercises([gym_user, bodyweight_user], count=6)

    assert gym_only.id not in {e.id for e in suggested}


@pytest.mark.asyncio
async def test_equipment_common_ground_is_shared(db_session) -> None:
    """A bodyweight exercise (no required items) is reachable for a gym
    member too -- pairing gym+bodyweight still shares it, unlike the
    gym-only case above."""
    gym_user = _make_user(has_gym_access=True)
    bodyweight_user = _make_user()
    shared_bodyweight, *shared_bodyweight_rows = _make_exercise(movement_pattern=_CLEAN_PATTERNS[0])
    _add(db_session, gym_user, bodyweight_user, (shared_bodyweight, *shared_bodyweight_rows))
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate(service, {"shared_bodyweight": shared_bodyweight})
    suggested = await service.suggest_party_exercises([gym_user, bodyweight_user], count=6)

    assert shared_bodyweight.id in {e.id for e in suggested}


@pytest.mark.asyncio
async def test_gym_member_alone_gets_the_gym_exercise(db_session) -> None:
    gym_user = _make_user(has_gym_access=True)
    gym_only, *gym_only_rows = _make_exercise(
        equipment_items=[EquipmentItem.BARBELL], movement_pattern=_CLEAN_PATTERNS[0]
    )
    _add(db_session, gym_user, (gym_only, *gym_only_rows))
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate(service, {"gym_only": gym_only})
    suggested = await service.suggest_party_exercises([gym_user], count=6)

    assert gym_only.id in {e.id for e in suggested}


@pytest.mark.asyncio
async def test_gym_access_alone_does_not_unlock_a_stick_required_exercise(db_session) -> None:
    """Personal-gear split (2026-08-22): PERSONAL_GEAR_ITEMS like a hockey
    stick must stay excluded from suggest_party_exercises' own gym-access
    bypass, same as list_for_assembly -- a gym doesn't stock sticks."""
    gym_user = _make_user(has_gym_access=True)
    stick_only, *stick_only_rows = _make_exercise(
        equipment_items=[EquipmentItem.HOCKEY_STICK], movement_pattern=_CLEAN_PATTERNS[0]
    )
    _add(db_session, gym_user, (stick_only, *stick_only_rows))
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate(service, {"stick_only": stick_only})
    suggested = await service.suggest_party_exercises([gym_user], count=6)

    assert stick_only.id not in {e.id for e in suggested}


@pytest.mark.asyncio
async def test_owning_a_stick_unlocks_it_even_with_gym_access(db_session) -> None:
    gym_user = _make_user(has_gym_access=True)
    db_session.add(gym_user)
    await db_session.flush()
    stick_only, *stick_only_rows = _make_exercise(
        equipment_items=[EquipmentItem.HOCKEY_STICK], movement_pattern=_CLEAN_PATTERNS[0]
    )
    _add(
        db_session,
        UserEquipmentItem(user_id=gym_user.id, equipment_item=EquipmentItem.HOCKEY_STICK),
        (stick_only, *stick_only_rows),
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate(service, {"stick_only": stick_only})
    suggested = await service.suggest_party_exercises([gym_user], count=6)

    assert stick_only.id in {e.id for e in suggested}


@pytest.mark.asyncio
async def test_difficulty_cap_uses_the_weakest_member(db_session) -> None:
    """level<8 caps difficulty at 2 (see max_difficulty_for_level) -- pairing
    a low-level member with a high-level one must still respect the low
    member's cap, never the high one's. Both exercises share one (clean)
    movement_pattern so they compete in the same pattern pool -- proves the
    exclusion is about difficulty, not just "different pattern got picked"."""
    weak = _make_user(level=1)
    strong = _make_user(level=20)
    easy, easy_pattern = _make_exercise(difficulty_level=2, movement_pattern=_CLEAN_PATTERNS[0])
    hard, hard_pattern = _make_exercise(difficulty_level=5, movement_pattern=_CLEAN_PATTERNS[0])
    _add(db_session, weak, strong, (easy, easy_pattern), (hard, hard_pattern))
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate(service, {"easy": easy, "hard": hard})
    suggested = await service.suggest_party_exercises([weak, strong], count=6)

    suggested_ids = {e.id for e in suggested}
    assert hard.id not in suggested_ids


@pytest.mark.asyncio
async def test_covers_distinct_movement_patterns(db_session) -> None:
    user = _make_user()
    pairs = [_make_exercise(movement_pattern=pattern) for pattern in _CLEAN_PATTERNS]
    pattern_by_id = {exercise.id: pattern for (exercise, _), pattern in zip(pairs, _CLEAN_PATTERNS)}
    _add(db_session, user, pairs)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate(service, {e.id: e for e, _ in pairs})
    suggested = await service.suggest_party_exercises([user], count=6)

    patterns = {pattern_by_id[e.id] for e in suggested if e.id in pattern_by_id}
    assert patterns == set(_CLEAN_PATTERNS)


@pytest.mark.asyncio
async def test_on_ice_exercises_are_never_suggested(db_session) -> None:
    user = _make_user()
    on_ice, on_ice_pattern = _make_exercise(
        category=ExerciseCategory.ON_ICE, movement_pattern=MovementPattern.LOCOMOTION
    )
    _add(db_session, user, (on_ice, on_ice_pattern))
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate(service, {"on_ice": on_ice})
    suggested = await service.suggest_party_exercises([user], count=6)

    assert on_ice.id not in {e.id for e in suggested}


@pytest.mark.asyncio
async def test_respects_count(db_session) -> None:
    user = _make_user()
    pairs = [
        _make_exercise(movement_pattern=pattern)
        for pattern in (
            MovementPattern.HIP_HINGE,
            MovementPattern.SQUAT,
            MovementPattern.PULL,
            MovementPattern.PUSH,
        )
    ]
    _add(db_session, user, pairs)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate(service, {e.id: e for e, _ in pairs})
    suggested = await service.suggest_party_exercises([user], count=2)

    assert len(suggested) == 2


@pytest.mark.asyncio
async def test_no_members_returns_empty(db_session) -> None:
    service = ScheduleService(db_session)
    assert await service.suggest_party_exercises([], count=6) == []
