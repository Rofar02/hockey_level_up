"""ScheduleService's puck-handling tail-on (P3 item #8):
_pick_puck_module_exercises / its call site in _build_training_session.

An optional extra 1-4 TrainingPhase.PUCK exercises appended to a normal
OFF_ICE session when the player owns a hockey stick -- not a new
DaySessionType. Candidates come from TrainingPhase.PUCK specifically
(the phase itself is the authoritative "puck-module content" tag, see
scripts/seed_exercises.py's _PHASE_OVERRIDES), never falls back to
unrelated MAIN exercises the way a soft "preferred pattern" would.

Same deterministic-random / isolated-candidate-pool / Latin-"A"-prefix
pattern as test_schedule_service_game_day.py, for the same reason (shared
dev DB with a real seeded catalog).
"""
import random
import uuid
from datetime import date, timedelta

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import (
    EquipmentItem,
    Exercise,
    ExerciseCategory,
    TrainingPhase,
    UserEquipmentItem,
)
from app.models.schedule import DaySessionType
from app.models.user import User
from app.schemas.schedule import DayPlanIn, WeeklyPlanCreate
from app.services.schedule_service import _PUCK_MODULE_MAX_EXERCISES, ScheduleService


@pytest.fixture(autouse=True)
def deterministic_random(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(random, "randint", lambda a, b: a)
    monkeypatch.setattr(random, "choice", lambda pool: sorted(pool, key=lambda e: e.name)[0])
    monkeypatch.setattr(random, "shuffle", lambda pool: pool.sort(key=lambda e: e.name))


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"puck_{unique}",
        email=f"puck_{unique}@example.com",
        password_hash="irrelevant",
        level=15,
    )


def _make_exercise(*, name: str, phase: TrainingPhase = TrainingPhase.PUCK) -> Exercise:
    return Exercise(
        id=uuid.uuid4(), name=name, category=ExerciseCategory.OFF_ICE, phase=phase, difficulty_level=1
    )


def _isolate_candidates(service: ScheduleService, exercises: dict[str, Exercise]) -> None:
    async def fake_list_for_assembly(
        *, phase, user, category=None, suitable_for_game_day=None
    ):
        pool = [e for e in exercises.values() if e.phase == phase]
        if category is not None:
            pool = [e for e in pool if e.category == category]
        return pool

    service._exercises.list_for_assembly = fake_list_for_assembly


@pytest.mark.asyncio
async def test_no_tail_on_when_stick_not_owned(db_session) -> None:
    user = _make_user()
    puck_exercise = _make_exercise(name="AAA puck drill")
    db_session.add_all([user, puck_exercise])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"puck": puck_exercise})
    picked = await service._pick_puck_module_exercises(user, BlockPhase.ACCUMULATION)

    assert picked == []


@pytest.mark.asyncio
async def test_tail_on_appears_when_stick_owned_and_candidates_exist(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    puck_exercise = _make_exercise(name="AAA puck drill")
    db_session.add_all([
        puck_exercise,
        UserEquipmentItem(user_id=user.id, equipment_item=EquipmentItem.HOCKEY_STICK),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"puck": puck_exercise})
    picked = await service._pick_puck_module_exercises(user, BlockPhase.ACCUMULATION)

    assert [e.id for e in picked] == [puck_exercise.id]


@pytest.mark.asyncio
async def test_empty_puck_pool_degrades_gracefully(db_session) -> None:
    """Stick owned, but no phase=PUCK candidates exist -- the thin real
    catalog's actual state today (only 3 real exercises total)."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    main_exercise = _make_exercise(name="AAA off-ice main", phase=TrainingPhase.MAIN)
    db_session.add_all([
        main_exercise,
        UserEquipmentItem(user_id=user.id, equipment_item=EquipmentItem.HOCKEY_STICK),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"main": main_exercise})
    picked = await service._pick_puck_module_exercises(user, BlockPhase.ACCUMULATION)

    assert picked == []


@pytest.mark.asyncio
async def test_never_falls_back_to_main_phase_exercises(db_session) -> None:
    """Unlike _pick_sequence's preferred_patterns, an empty PUCK pool must
    never spill into MAIN candidates to pad the count."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    main_exercise = _make_exercise(name="AAA off-ice filler", phase=TrainingPhase.MAIN)
    db_session.add_all([
        main_exercise, UserEquipmentItem(user_id=user.id, equipment_item=EquipmentItem.HOCKEY_STICK)
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"main": main_exercise})
    picked = await service._pick_puck_module_exercises(user, BlockPhase.ACCUMULATION)

    assert main_exercise.id not in {e.id for e in picked}
    assert picked == []


@pytest.mark.asyncio
async def test_capped_at_max_exercises(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    exercises = {
        f"puck_{i}": _make_exercise(name=f"AAA{i:02d} puck drill")
        for i in range(_PUCK_MODULE_MAX_EXERCISES + 3)
    }
    db_session.add(UserEquipmentItem(user_id=user.id, equipment_item=EquipmentItem.HOCKEY_STICK))
    db_session.add_all(exercises.values())
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_puck_module_exercises(user, BlockPhase.ACCUMULATION)

    assert len(picked) == _PUCK_MODULE_MAX_EXERCISES


@pytest.mark.asyncio
async def test_create_weekly_plan_off_ice_day_includes_tail_on_when_stick_owned(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    puck_exercise = _make_exercise(name="AAA puck drill")
    off_ice_main = _make_exercise(name="AAA off-ice main", phase=TrainingPhase.MAIN)
    db_session.add_all([
        puck_exercise,
        off_ice_main,
        UserEquipmentItem(user_id=user.id, equipment_item=EquipmentItem.HOCKEY_STICK),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"puck": puck_exercise, "main": off_ice_main})

    monday = date(2026, 3, 9)
    days = [
        DayPlanIn(date=monday, session_type=DaySessionType.OFF_ICE),
        *[
            DayPlanIn(date=monday + timedelta(days=offset), session_type=DaySessionType.REST)
            for offset in range(1, 7)
        ],
    ]
    result = await service.create_weekly_plan(user, WeeklyPlanCreate(days=days))

    off_ice_day = result.day_plans[0]
    puck_ids = {
        block.exercise.id
        for block in off_ice_day.training_session.blocks
        if block.phase == TrainingPhase.PUCK
    }
    # off_ice_main isn't asserted into MAIN here -- untagged with any
    # MovementPattern, so _pick_main's own role-filling (out of scope for
    # this test) may or may not select it; what this test actually proves
    # is the PUCK tail-on landing correctly through the real
    # create_weekly_plan path.
    assert puck_ids == {puck_exercise.id}


@pytest.mark.asyncio
async def test_create_weekly_plan_off_ice_day_no_puck_block_without_stick(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    puck_exercise = _make_exercise(name="AAA puck drill")
    off_ice_main = _make_exercise(name="AAA off-ice main", phase=TrainingPhase.MAIN)
    db_session.add_all([puck_exercise, off_ice_main])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"puck": puck_exercise, "main": off_ice_main})

    monday = date(2026, 3, 16)
    days = [
        DayPlanIn(date=monday, session_type=DaySessionType.OFF_ICE),
        *[
            DayPlanIn(date=monday + timedelta(days=offset), session_type=DaySessionType.REST)
            for offset in range(1, 7)
        ],
    ]
    result = await service.create_weekly_plan(user, WeeklyPlanCreate(days=days))

    off_ice_day = result.day_plans[0]
    assert all(block.phase != TrainingPhase.PUCK for block in off_ice_day.training_session.blocks)
