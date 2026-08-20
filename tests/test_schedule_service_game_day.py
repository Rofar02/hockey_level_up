"""ScheduleService's GAME-day path (_build_session_for_day / _build_game_day_session):

GAME is a light pre-game day, not a workout -- no main block, no cooldown,
and physical activation is pulled from both on-ice and off-ice warmup pools
since GAME has no ExerciseCategory of its own. The activation pick is
further filtered to Exercise.suitable_for_game_day=True, not just
phase=WARMUP -- a plain warmup exercise (e.g. loaded barbell work meant to
prep for a full session) isn't necessarily light enough for pre-game
activation, so it has to be explicitly marked, and defaults to False for
every exercise (including the whole real catalog, via the migration's
server_default). A separate optional pick covers "mental prep" (a warmup
exercise targeting intellect, unfiltered by suitable_for_game_day per
spec), which must degrade gracefully (no exception) when the catalog has
none yet -- exactly the current state of the real catalog.

These tests run against the same shared dev DB as test_schedule_service_pick_main.py,
which already has a real seeded exercise catalog -- so, same as that file,
`random.choice`/`random.randint` are monkeypatched to a deterministic,
name-sorted pick, and this file's own fixtures are named with a Latin "A"
prefix (sorts before every Cyrillic catalog name in a plain Python string
sort) so assertions can pin exactly which exercise gets picked.
"""
import random
import uuid
from datetime import date, timedelta

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseTargetStat,
    TargetStat,
    TrainingPhase,
)
from app.models.schedule import DaySessionType
from app.models.user import User
from app.schemas.schedule import DayPlanIn, WeeklyPlanCreate
from app.services.schedule_service import ScheduleService


@pytest.fixture(autouse=True)
def deterministic_random(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(random, "randint", lambda a, b: a)
    monkeypatch.setattr(random, "choice", lambda pool: sorted(pool, key=lambda e: e.name)[0])


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"gameday_{unique}",
        email=f"gameday_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise(
    *,
    name: str,
    category: ExerciseCategory,
    phase: TrainingPhase,
    suitable_for_game_day: bool = False,
) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=category,
        phase=phase,
        difficulty_level=1,
        suitable_for_game_day=suitable_for_game_day,
    )


def _isolate_candidates(service: ScheduleService, exercises: dict[str, Exercise]) -> None:
    """Make list_for_assembly return only this test's own exercises, filtered
    the same way the real repository method would. The real dev DB now has a
    real seeded catalog including off_ice/warmup/suitable_for_game_day=True
    content (see the 90-exercise import) and off_ice intellect-tagged
    exercises, both of which would otherwise leak into these tests' pools
    and break assertions like "exactly these two ids" or "no candidate at
    all" -- same isolation pattern as test_pick_main_periodization.py/
    test_level_difficulty_gate.py."""

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


async def _seed_activation_pool(db_session) -> dict[str, Exercise]:
    """One "AAA"-prefixed, suitable_for_game_day=True warmup exercise per
    category (guaranteed to win the deterministic name-sort over the real
    catalog, all of which defaults to suitable_for_game_day=False), plus a
    main/cooldown exercise per category so a GAME day that incorrectly fell
    back to the regular on/off-ice builder would visibly pick those up too."""
    exercises = {
        "on_ice_warmup": _make_exercise(
            name="AAA on-ice warmup",
            category=ExerciseCategory.ON_ICE,
            phase=TrainingPhase.WARMUP,
            suitable_for_game_day=True,
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
            suitable_for_game_day=True,
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
async def test_game_day_has_no_main_or_cooldown_blocks(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = await _seed_activation_pool(db_session)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    session = await service._build_game_day_session(user, BlockPhase.ACCUMULATION)

    assert len(session.blocks) > 0  # both warmup pools had a candidate
    assert all(block.phase == TrainingPhase.WARMUP for block in session.blocks)


@pytest.mark.asyncio
async def test_game_day_pulls_activation_from_both_ice_and_off_ice(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = await _seed_activation_pool(db_session)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    session = await service._build_game_day_session(user, BlockPhase.ACCUMULATION)

    picked_ids = [block.exercise_id for block in session.blocks]
    assert picked_ids == [exercises["on_ice_warmup"].id, exercises["off_ice_warmup"].id]


@pytest.mark.asyncio
async def test_warmup_exercise_without_flag_is_excluded_from_activation(db_session) -> None:
    """phase=WARMUP alone is no longer enough -- an unflagged warmup
    exercise (the default for every exercise, including the whole real
    catalog after the migration) must not be picked for GAME-day
    activation, even though it would be picked for a regular on/off-ice
    day's warmup."""
    user = _make_user()
    db_session.add(user)
    unflagged = _make_exercise(
        name="AAA unflagged on-ice warmup",
        category=ExerciseCategory.ON_ICE,
        phase=TrainingPhase.WARMUP,
        # suitable_for_game_day left at its default: False.
    )
    db_session.add(unflagged)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"unflagged": unflagged})
    session = await service._build_game_day_session(user, BlockPhase.ACCUMULATION)

    picked_ids = {block.exercise_id for block in session.blocks}
    assert unflagged.id not in picked_ids
    # Sorts first alphabetically among on-ice warmups, so its absence here
    # proves the filter -- not just "something else got picked instead".
    assert session.blocks == []


@pytest.mark.asyncio
async def test_warmup_exercise_with_flag_is_included_in_activation(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    flagged = _make_exercise(
        name="AAA flagged on-ice warmup",
        category=ExerciseCategory.ON_ICE,
        phase=TrainingPhase.WARMUP,
        suitable_for_game_day=True,
    )
    unflagged = _make_exercise(
        name="AAA unflagged on-ice warmup",
        category=ExerciseCategory.ON_ICE,
        phase=TrainingPhase.WARMUP,
    )
    db_session.add_all([flagged, unflagged])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"flagged": flagged, "unflagged": unflagged})
    session = await service._build_game_day_session(user, BlockPhase.ACCUMULATION)

    picked_ids = [block.exercise_id for block in session.blocks]
    assert picked_ids == [flagged.id]


@pytest.mark.asyncio
async def test_game_day_includes_mental_prep_when_catalog_has_one(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = await _seed_activation_pool(db_session)
    # Named "ZZZ..." (sorts last), not "AAA..." like the activation pool --
    # otherwise this would win the *physical* off-ice warmup slot outright
    # (that pick isn't filtered by target_stat), leaving nothing for the
    # dedicated intellect-only search to find.
    mental_exercise = _make_exercise(
        name="ZZZ mental prep",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.WARMUP,
        # suitable_for_game_day intentionally left False -- per spec,
        # _pick_mental_prep is unfiltered by it (target_stat=intellect is
        # already specific enough).
    )
    db_session.add(mental_exercise)
    db_session.add(
        ExerciseTargetStat(
            exercise_id=mental_exercise.id, target_stat=TargetStat.INTELLECT, order=0
        )
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {**exercises, "mental": mental_exercise})
    session = await service._build_game_day_session(user, BlockPhase.ACCUMULATION)

    picked_ids = [block.exercise_id for block in session.blocks]
    assert picked_ids == [
        exercises["on_ice_warmup"].id,
        exercises["off_ice_warmup"].id,
        mental_exercise.id,
    ]


@pytest.mark.asyncio
async def test_game_day_mental_prep_gracefully_skipped_when_catalog_has_none(db_session) -> None:
    """No exercise anywhere -- real catalog included -- has target_stat=intellect
    in the warmup phase today (verified: the real catalog's warmup rows are
    only agility/endurance/strength). _pick_mental_prep must return None
    rather than raise, and the session still builds with activation only."""
    user = _make_user()
    db_session.add(user)
    exercises = await _seed_activation_pool(db_session)  # no intellect exercise among these
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    session = await service._build_game_day_session(user, BlockPhase.ACCUMULATION)

    picked_ids = [block.exercise_id for block in session.blocks]
    assert picked_ids == [exercises["on_ice_warmup"].id, exercises["off_ice_warmup"].id]


@pytest.mark.asyncio
async def test_create_weekly_plan_game_day_round_trips_with_warmup_only_split(db_session) -> None:
    """End-to-end through create_weekly_plan + _to_read_schema -- exercises
    the GAME branch of the phase_split fix (no ExerciseCategory to key off
    for GAME, unlike ON_ICE/OFF_ICE), not just the block-assembly helper in
    isolation above."""
    user = _make_user()
    db_session.add(user)
    await _seed_activation_pool(db_session)
    await db_session.flush()

    monday = date(2026, 3, 9)
    days = [
        DayPlanIn(date=monday, session_type=DaySessionType.GAME),
        *[
            DayPlanIn(date=monday + timedelta(days=offset), session_type=DaySessionType.REST)
            for offset in range(1, 7)
        ],
    ]

    service = ScheduleService(db_session)
    result = await service.create_weekly_plan(user, WeeklyPlanCreate(days=days))

    game_day = result.day_plans[0]
    assert game_day.session_type == DaySessionType.GAME
    assert game_day.training_session is not None
    assert all(block.phase == TrainingPhase.WARMUP for block in game_day.training_session.blocks)
    assert game_day.training_session.phase_split == {TrainingPhase.WARMUP: 1.0}
