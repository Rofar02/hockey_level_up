"""ScheduleService.suggest_party_exercises: the co-op exercise-suggestion
engine behind TrainingPartyService.suggest_exercises. Equipment is treated as
cumulative capability (gym implies home implies bodyweight, see
_EQUIPMENT_REACH) rather than list_for_assembly's single-user exact match --
see that method's docstring for why -- and difficulty is capped at the
weakest member's ceiling, never relaxed.
"""
import uuid

import pytest

from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TargetStat, TrainingPhase
from app.models.user import User
from app.services.schedule_service import ScheduleService

# The dev/test Postgres database already has seeded off_ice/MAIN exercises
# for STRENGTH/AGILITY/ENDURANCE (see scripts/seed_exercises.py) -- tests
# that need an exact, uncontaminated candidate pool use these three stats
# instead, which the seed data never touches for off_ice/MAIN.
_CLEAN_STATS = (TargetStat.INTELLECT, TargetStat.ON_ICE_SKATING, TargetStat.PUCK_HANDLING)


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"suggest_{unique}",
        email=f"suggest_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        friend_code=unique.upper(),
        level=1,
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_exercise(**overrides) -> Exercise:
    defaults = dict(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        target_stat=TargetStat.STRENGTH,
        difficulty_level=1,
        equipment_type=EquipmentType.BODYWEIGHT,
    )
    defaults.update(overrides)
    return Exercise(**defaults)


@pytest.mark.asyncio
async def test_equipment_without_common_ground_excludes_gym_only_exercise(db_session) -> None:
    """A gym-only exercise is dropped once a bodyweight-only member is in the
    party, even though a gym member alone would see it -- the member without
    the equipment excludes it from the shared set. Both exercises share one
    (clean) target_stat so they compete in the same stat pool -- proves the
    exclusion is about equipment, not just "different stat got picked"."""
    gym_user = _make_user(equipment_access=EquipmentType.GYM)
    bodyweight_user = _make_user(equipment_access=EquipmentType.BODYWEIGHT)
    gym_only = _make_exercise(equipment_type=EquipmentType.GYM, target_stat=_CLEAN_STATS[0])
    db_session.add_all([gym_user, bodyweight_user, gym_only])
    await db_session.flush()

    service = ScheduleService(db_session)
    suggested = await service.suggest_party_exercises([gym_user, bodyweight_user], count=6)

    assert gym_only.id not in {e.id for e in suggested}


@pytest.mark.asyncio
async def test_equipment_common_ground_is_shared(db_session) -> None:
    """A bodyweight exercise is reachable for a gym member too (cumulative
    capability, see _EQUIPMENT_REACH) -- pairing gym+bodyweight still shares
    it, unlike the gym-only case above."""
    gym_user = _make_user(equipment_access=EquipmentType.GYM)
    bodyweight_user = _make_user(equipment_access=EquipmentType.BODYWEIGHT)
    shared_bodyweight = _make_exercise(
        equipment_type=EquipmentType.BODYWEIGHT, target_stat=_CLEAN_STATS[0]
    )
    db_session.add_all([gym_user, bodyweight_user, shared_bodyweight])
    await db_session.flush()

    service = ScheduleService(db_session)
    suggested = await service.suggest_party_exercises([gym_user, bodyweight_user], count=6)

    assert shared_bodyweight.id in {e.id for e in suggested}


@pytest.mark.asyncio
async def test_gym_member_alone_gets_the_gym_exercise(db_session) -> None:
    gym_user = _make_user(equipment_access=EquipmentType.GYM)
    gym_only = _make_exercise(equipment_type=EquipmentType.GYM, target_stat=_CLEAN_STATS[0])
    db_session.add_all([gym_user, gym_only])
    await db_session.flush()

    service = ScheduleService(db_session)
    suggested = await service.suggest_party_exercises([gym_user], count=6)

    assert gym_only.id in {e.id for e in suggested}


@pytest.mark.asyncio
async def test_difficulty_cap_uses_the_weakest_member(db_session) -> None:
    """level<8 caps difficulty at 2 (see max_difficulty_for_level) -- pairing
    a low-level member with a high-level one must still respect the low
    member's cap, never the high one's. Both exercises share one (clean)
    target_stat so they compete in the same stat pool -- proves the
    exclusion is about difficulty, not just "different stat got picked"."""
    weak = _make_user(level=1)
    strong = _make_user(level=20)
    easy = _make_exercise(difficulty_level=2, target_stat=_CLEAN_STATS[0])
    hard = _make_exercise(difficulty_level=5, target_stat=_CLEAN_STATS[0])
    db_session.add_all([weak, strong, easy, hard])
    await db_session.flush()

    service = ScheduleService(db_session)
    suggested = await service.suggest_party_exercises([weak, strong], count=6)

    suggested_ids = {e.id for e in suggested}
    assert hard.id not in suggested_ids


@pytest.mark.asyncio
async def test_covers_distinct_target_stats(db_session) -> None:
    user = _make_user()
    exercises = [_make_exercise(target_stat=stat) for stat in _CLEAN_STATS]
    db_session.add_all([user, *exercises])
    await db_session.flush()

    service = ScheduleService(db_session)
    suggested = await service.suggest_party_exercises([user], count=6)

    stats = {e.target_stat for e in suggested if e.id in {ex.id for ex in exercises}}
    assert stats == set(_CLEAN_STATS)


@pytest.mark.asyncio
async def test_on_ice_exercises_are_never_suggested(db_session) -> None:
    user = _make_user()
    on_ice = _make_exercise(category=ExerciseCategory.ON_ICE, target_stat=TargetStat.ON_ICE_SKATING)
    db_session.add_all([user, on_ice])
    await db_session.flush()

    service = ScheduleService(db_session)
    suggested = await service.suggest_party_exercises([user], count=6)

    assert on_ice.id not in {e.id for e in suggested}


@pytest.mark.asyncio
async def test_respects_count(db_session) -> None:
    user = _make_user()
    exercises = [
        _make_exercise(target_stat=stat)
        for stat in (TargetStat.STRENGTH, TargetStat.AGILITY, TargetStat.ENDURANCE, TargetStat.INTELLECT)
    ]
    db_session.add_all([user, *exercises])
    await db_session.flush()

    service = ScheduleService(db_session)
    suggested = await service.suggest_party_exercises([user], count=2)

    assert len(suggested) == 2


@pytest.mark.asyncio
async def test_no_members_returns_empty(db_session) -> None:
    service = ScheduleService(db_session)
    assert await service.suggest_party_exercises([], count=6) == []
