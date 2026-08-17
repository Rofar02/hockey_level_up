"""Phase: П.4 seasonal mode -- ScheduleService._pick_main's off-ice volume
ceiling tightens during SEASON/PLAYOFFS (see
app.core.training_block.main_exercise_count_range). ON_ICE and
OFFSEASON/PRESEASON are never affected. Same
_isolate_candidates/movement-pattern-per-candidate setup as
test_pick_main_movement_pattern_axis.py -- 5 distinct off-ice patterns so
the unclamped range (5-6 in accumulation) would otherwise be fully
reachable, making a lower observed count attributable only to the season
clamp.
"""
import uuid

import pytest

from app.models.exercise import (
    EquipmentType,
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    MovementPattern,
    TrainingPhase,
)
from app.models.schedule import BlockPhase
from app.models.user import SeasonPeriod, User
from app.services.schedule_service import ScheduleService

_PATTERNS = [
    MovementPattern.HIP_HINGE,
    MovementPattern.SQUAT,
    MovementPattern.PUSH,
    MovementPattern.PULL,
    MovementPattern.ROTATION,
]


def _make_user(*, season_period: SeasonPeriod) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"season_{unique}",
        email=f"season_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        level=15,
        season_period=season_period,
    )


def _make_exercise(name: str, *, category: ExerciseCategory = ExerciseCategory.OFF_ICE) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=category,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        equipment_type=EquipmentType.BODYWEIGHT,
    )


async def _seed_candidates(db_session, *, category: ExerciseCategory) -> list[Exercise]:
    exercises = [_make_exercise(f"main-{pattern.value}", category=category) for pattern in _PATTERNS]
    db_session.add_all(exercises)
    db_session.add_all([
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=pattern)
        for exercise, pattern in zip(exercises, _PATTERNS)
    ])
    await db_session.flush()
    return exercises


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, equipment_access, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


@pytest.mark.asyncio
async def test_playoffs_caps_off_ice_main_block_at_deload_range(db_session) -> None:
    user = _make_user(season_period=SeasonPeriod.PLAYOFFS)
    db_session.add(user)
    exercises = await _seed_candidates(db_session, category=ExerciseCategory.OFF_ICE)

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    # MAIN_EXERCISE_COUNT_RANGE[ACCUMULATION] is (5, 6) unclamped -- 5
    # distinct-pattern candidates exist, so anything above 4 here would
    # prove the playoffs clamp did NOT apply.
    assert len(picked) <= 4


@pytest.mark.asyncio
async def test_season_caps_off_ice_main_block_below_normal_accumulation(db_session) -> None:
    user = _make_user(season_period=SeasonPeriod.SEASON)
    db_session.add(user)
    exercises = await _seed_candidates(db_session, category=ExerciseCategory.OFF_ICE)

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    # season shifts accumulation to intensification's (4, 5) range --
    # milder than playoffs' (3, 4), but still below the unclamped 5-6.
    assert len(picked) <= 5


@pytest.mark.asyncio
async def test_playoffs_does_not_affect_on_ice_main_block(db_session) -> None:
    user = _make_user(season_period=SeasonPeriod.PLAYOFFS)
    db_session.add(user)
    exercises = await _seed_candidates(db_session, category=ExerciseCategory.ON_ICE)

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.ON_ICE, user, BlockPhase.ACCUMULATION)

    # All 5 on-ice candidates must remain reachable -- the clamp is
    # off-ice-only.
    assert len(picked) == 5


@pytest.mark.asyncio
async def test_offseason_does_not_clamp_off_ice_main_block(db_session) -> None:
    user = _make_user(season_period=SeasonPeriod.OFFSEASON)
    db_session.add(user)
    exercises = await _seed_candidates(db_session, category=ExerciseCategory.OFF_ICE)

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert len(picked) == 5
