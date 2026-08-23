"""ScheduleService's ON_ICE-day path (_build_session_for_day /
_build_on_ice_day_session):

Real ice time is always a coach-run team practice -- the app has no
content for the practice itself, so an ON_ICE day is wrapped in an on-ice
warmup + cooldown only, no MAIN block. Unlike GAME (location-ambiguous,
single light activation pick), this is definitely an on-ice day, so it
gets the same full RAMP-protocol warmup complex a regular on-ice session
would have gotten under the old (pre-2026-08-23) MAIN-generating builder.

Same deterministic-random / isolated-candidate-pool / Latin-"A"-prefix
pattern as test_schedule_service_game_day.py, for the same reason (shared
dev DB with a real seeded catalog).
"""
import random
import uuid
from datetime import date, timedelta

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import Exercise, ExerciseCategory, TrainingPhase, WarmupStage
from app.models.schedule import DaySessionType
from app.models.user import User
from app.schemas.schedule import DayPlanIn, WeeklyPlanCreate
from app.services.schedule_service import ScheduleService


@pytest.fixture(autouse=True)
def deterministic_random(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(random, "randint", lambda a, b: a)
    monkeypatch.setattr(random, "choice", lambda pool: sorted(pool, key=lambda e: e.name)[0])
    monkeypatch.setattr(random, "shuffle", lambda pool: pool.sort(key=lambda e: e.name))


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"oniceday_{unique}",
        email=f"oniceday_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise(
    *,
    name: str,
    category: ExerciseCategory,
    phase: TrainingPhase,
    warmup_stage: WarmupStage | None = None,
) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=category,
        phase=phase,
        difficulty_level=1,
        warmup_stage=warmup_stage,
    )


def _isolate_candidates(service: ScheduleService, exercises: dict[str, Exercise]) -> None:
    """Same isolation pattern as test_schedule_service_game_day.py's own
    helper -- keeps the real seeded catalog from leaking into this file's
    "exactly these ids" assertions."""

    async def fake_list_for_assembly(
        *, phase, user, category=None, suitable_for_game_day=None
    ):
        pool = [e for e in exercises.values() if e.phase == phase]
        if category is not None:
            pool = [e for e in pool if e.category == category]
        if suitable_for_game_day is not None:
            pool = [e for e in pool if e.suitable_for_game_day == suitable_for_game_day]
        return pool

    service._exercises.list_for_assembly = fake_list_for_assembly


async def _seed_pool(db_session) -> dict[str, Exercise]:
    """One "AAA"-prefixed on-ice warmup exercise (RAISE stage, guaranteed to
    win the deterministic name-sort) and one on-ice cooldown exercise, plus
    an on-ice MAIN and a full off-ice set (warmup/main/cooldown) so an
    ON_ICE day that incorrectly still built a MAIN block, or incorrectly
    pulled from off-ice, would visibly pick those up too."""
    exercises = {
        "on_ice_warmup": _make_exercise(
            name="AAA on-ice warmup",
            category=ExerciseCategory.ON_ICE,
            phase=TrainingPhase.WARMUP,
            warmup_stage=WarmupStage.RAISE,
        ),
        "on_ice_main": _make_exercise(
            name="AAA on-ice main", category=ExerciseCategory.ON_ICE, phase=TrainingPhase.MAIN
        ),
        "on_ice_cooldown": _make_exercise(
            name="AAA on-ice cooldown", category=ExerciseCategory.ON_ICE, phase=TrainingPhase.COOLDOWN
        ),
        "off_ice_warmup": _make_exercise(
            name="AAA off-ice warmup",
            category=ExerciseCategory.OFF_ICE,
            phase=TrainingPhase.WARMUP,
            warmup_stage=WarmupStage.RAISE,
        ),
        "off_ice_main": _make_exercise(
            name="AAA off-ice main", category=ExerciseCategory.OFF_ICE, phase=TrainingPhase.MAIN
        ),
        "off_ice_cooldown": _make_exercise(
            name="AAA off-ice cooldown", category=ExerciseCategory.OFF_ICE, phase=TrainingPhase.COOLDOWN
        ),
    }
    db_session.add_all(exercises.values())
    await db_session.flush()
    return exercises


@pytest.mark.asyncio
async def test_on_ice_day_has_no_main_block(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = await _seed_pool(db_session)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    session = await service._build_on_ice_day_session(user, BlockPhase.ACCUMULATION)

    assert len(session.blocks) > 0
    assert all(block.phase != TrainingPhase.MAIN for block in session.blocks)


@pytest.mark.asyncio
async def test_on_ice_day_pulls_only_from_on_ice_pool(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = await _seed_pool(db_session)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    session = await service._build_on_ice_day_session(user, BlockPhase.ACCUMULATION)

    picked_ids = {block.exercise_id for block in session.blocks}
    assert picked_ids == {exercises["on_ice_warmup"].id, exercises["on_ice_cooldown"].id}
    assert exercises["off_ice_warmup"].id not in picked_ids
    assert exercises["off_ice_cooldown"].id not in picked_ids


@pytest.mark.asyncio
async def test_on_ice_day_warmup_precedes_cooldown_in_block_order(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = await _seed_pool(db_session)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    session = await service._build_on_ice_day_session(user, BlockPhase.ACCUMULATION)

    phases_in_order = [block.phase for block in sorted(session.blocks, key=lambda b: b.order)]
    assert phases_in_order == [TrainingPhase.WARMUP, TrainingPhase.COOLDOWN]


@pytest.mark.asyncio
async def test_create_weekly_plan_on_ice_day_round_trips(db_session) -> None:
    """End-to-end through create_weekly_plan + _to_read_schema -- exercises
    the generic compute_phase_split path (no GAME-style special-casing
    needed for a WARMUP+COOLDOWN mix), and confirms _build_session_for_day
    actually dispatches ON_ICE to the no-MAIN builder rather than the
    regular _build_training_session."""
    user = _make_user()
    db_session.add(user)
    await _seed_pool(db_session)
    await db_session.flush()

    monday = date(2026, 3, 9)
    days = [
        DayPlanIn(date=monday, session_type=DaySessionType.ON_ICE),
        *[
            DayPlanIn(date=monday + timedelta(days=offset), session_type=DaySessionType.REST)
            for offset in range(1, 7)
        ],
    ]

    service = ScheduleService(db_session)
    result = await service.create_weekly_plan(user, WeeklyPlanCreate(days=days))

    on_ice_day = result.day_plans[0]
    assert on_ice_day.session_type == DaySessionType.ON_ICE
    assert on_ice_day.training_session is not None
    blocks = on_ice_day.training_session.blocks
    assert all(block.phase != TrainingPhase.MAIN for block in blocks)
    assert {block.phase for block in blocks} == {TrainingPhase.WARMUP, TrainingPhase.COOLDOWN}
