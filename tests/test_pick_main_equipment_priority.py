"""_pick_main's gym-access light-substitute deprioritization (2026-09-21):
with a real gym available, a "real" gym exercise on a pattern should win
over a light substitute (resistance band, jump rope, foam roller, slide
board, step platform) tagged on that same pattern -- previously
random.choice gave them equal odds even with has_gym_access=True. See
LIGHT_SUBSTITUTE_EQUIPMENT in app/models/exercise.py and the filter in
ScheduleService._pick_main's pick_for_pattern closure.

Both exercises here are tagged on MovementPattern.CORE, a role-4-only
pattern (see test_pick_main_muscle_balance.py's own docstring for why that
isolates the pick to role 4 with no role 1-3 interference).

random.choice is monkeypatched to alphabetical-first, same as
test_pick_main_muscle_balance.py -- the resistance-band exercise is named
alphabetically first so a pass here proves the equipment filter actually
ran, not that it coincided with the deterministic tie-break.
"""
import random
import uuid

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import (
    EquipmentItem,
    Exercise,
    ExerciseCategory,
    ExerciseEquipmentItem,
    ExerciseMovementPattern,
    MovementPattern,
    TrainingPhase,
)
from app.models.user import User
from app.services.schedule_service import ScheduleService


@pytest.fixture(autouse=True)
def deterministic_random(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(random, "randint", lambda a, b: 3)
    monkeypatch.setattr(random, "choice", lambda pool: sorted(pool, key=lambda e: e.name)[0])
    monkeypatch.setattr(random, "shuffle", lambda seq: None)


def _make_user(*, has_gym_access: bool) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"user_{unique}",
        email=f"user_{unique}@example.com",
        password_hash="irrelevant",
        has_gym_access=has_gym_access,
    )


def _make_exercise(name: str, equipment_item: EquipmentItem) -> tuple[
    Exercise, ExerciseMovementPattern, ExerciseEquipmentItem
]:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )
    return (
        exercise,
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.CORE),
        ExerciseEquipmentItem(exercise_id=exercise.id, equipment_item=equipment_item),
    )


def _add_all(
    db_session,
    rows: list[tuple[Exercise, ExerciseMovementPattern, ExerciseEquipmentItem]],
) -> list[Exercise]:
    db_session.add_all([e for e, _, _ in rows])
    db_session.add_all([p for _, p, _ in rows])
    db_session.add_all([eq for _, _, eq in rows])
    return [e for e, _, _ in rows]


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    """Make list_for_assembly return only this test's own exercises -- see
    test_pick_main_muscle_balance.py's identical helper for why (the real
    dev DB's seeded catalog would otherwise leak extra CORE candidates in
    and break the "only these two compete" assertions)."""

    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


@pytest.mark.asyncio
async def test_gym_access_prefers_real_equipment_over_light_substitute(db_session) -> None:
    user = _make_user(has_gym_access=True)
    db_session.add(user)
    exercises = _add_all(db_session, [
        _make_exercise("A-band-core", EquipmentItem.RESISTANCE_BAND),
        _make_exercise("B-machine-core", EquipmentItem.GYM_MACHINE),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["B-machine-core"]


@pytest.mark.asyncio
async def test_no_gym_access_keeps_light_substitute_in_pool(db_session) -> None:
    user = _make_user(has_gym_access=False)
    db_session.add(user)
    exercises = _add_all(db_session, [
        _make_exercise("A-band-core", EquipmentItem.RESISTANCE_BAND),
        _make_exercise("B-machine-core", EquipmentItem.GYM_MACHINE),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["A-band-core"]
