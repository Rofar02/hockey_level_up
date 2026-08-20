"""Phase 3: warmup/cooldown chosen retrospectively to match MAIN's
movement_pattern, in ScheduleService._build_training_session/_pick_single.

MAIN is picked first; warmup and cooldown then each prefer, from their own
curated pool, an exercise sharing at least one movement_pattern with
whatever MAIN ended up with -- falling back to the untouched pool (today's
plain random pick) whenever nothing in it overlaps, same fallback shape as
every other priority layer in _pick_single/_pick_main.

Same isolation approach as test_schedule_service_game_day.py: the real dev
DB has a real seeded catalog now (see scripts/backfill_exercise_metadata.py),
so list_for_assembly and list_movement_patterns_by_exercise are both faked
to serve only this file's own exercises.
"""
import random
import uuid

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseTargetStat,
    MovementPattern,
    TargetStat,
    TrainingPhase,
    WarmupStage,
)
from app.models.schedule import DaySessionType
from app.models.user import User
from app.services.schedule_service import ScheduleService


@pytest.fixture(autouse=True)
def deterministic_random(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(random, "randint", lambda a, b: 1)
    monkeypatch.setattr(random, "choice", lambda pool: sorted(pool, key=lambda e: e.name)[0])


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"warmup_match_{unique}",
        email=f"warmup_match_{unique}@example.com",
        password_hash="irrelevant",
        level=15,
    )


def _make_exercise(
    *, name: str, phase: TrainingPhase, warmup_stage: WarmupStage | None = None
) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=phase,
        difficulty_level=1,
        warmup_stage=warmup_stage,
    )


def _isolate_candidates(service: ScheduleService, exercises: dict[str, Exercise]) -> None:
    """Same isolation pattern as test_schedule_service_game_day.py's
    _isolate_candidates -- fakes both repository methods this feature reads,
    so the real seeded catalog's own movement_pattern rows can't leak in."""

    async def fake_list_for_assembly(
        *, phase, user, category=None, suitable_for_game_day=None
    ):
        pool = [e for e in exercises.values() if e.phase == phase]
        if category is not None:
            pool = [e for e in pool if e.category == category]
        return pool

    async def fake_list_movement_patterns_by_exercise(exercise_ids):
        by_id = {e.id: e for e in exercises.values()}
        return {
            eid: list(PATTERNS_BY_NAME.get(by_id[eid].name, []))
            for eid in exercise_ids
            if eid in by_id and by_id[eid].name in PATTERNS_BY_NAME
        }

    service._exercises.list_for_assembly = fake_list_for_assembly
    service._exercises.list_movement_patterns_by_exercise = fake_list_movement_patterns_by_exercise


PATTERNS_BY_NAME: dict[str, list[MovementPattern]] = {}


@pytest.mark.asyncio
async def test_warmup_and_cooldown_prefer_exercise_sharing_main_pattern(db_session) -> None:
    user = _make_user()
    db_session.add(user)

    main = _make_exercise(name="AAA main squat", phase=TrainingPhase.MAIN)
    # Same warmup_stage on both -- _pick_warmup_complex picks at most one
    # exercise per stage, so this proves the pattern-matching one wins the
    # stage rather than just "both get picked" (there's only one slot to win).
    warmup_match = _make_exercise(
        name="Z warmup squat mobility", phase=TrainingPhase.WARMUP, warmup_stage=WarmupStage.DYNAMIC
    )
    warmup_other = _make_exercise(
        name="A warmup unrelated", phase=TrainingPhase.WARMUP, warmup_stage=WarmupStage.DYNAMIC
    )
    cooldown_match = _make_exercise(name="Z cooldown squat stretch", phase=TrainingPhase.COOLDOWN)
    cooldown_other = _make_exercise(name="A cooldown unrelated", phase=TrainingPhase.COOLDOWN)

    exercises = {
        "main": main,
        "warmup_match": warmup_match,
        "warmup_other": warmup_other,
        "cooldown_match": cooldown_match,
        "cooldown_other": cooldown_other,
    }
    db_session.add_all(exercises.values())
    db_session.add(ExerciseTargetStat(exercise_id=main.id, target_stat=TargetStat.STRENGTH, order=0))
    await db_session.flush()

    PATTERNS_BY_NAME.clear()
    PATTERNS_BY_NAME[main.name] = [MovementPattern.SQUAT]
    PATTERNS_BY_NAME[warmup_match.name] = [MovementPattern.SQUAT, MovementPattern.HIP_MOBILITY]
    PATTERNS_BY_NAME[warmup_other.name] = [MovementPattern.PULL]
    PATTERNS_BY_NAME[cooldown_match.name] = [MovementPattern.SQUAT]
    PATTERNS_BY_NAME[cooldown_other.name] = [MovementPattern.PUSH]

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    session = await service._build_training_session(
        session_type=DaySessionType.OFF_ICE,
        user=user,
        block_phase=BlockPhase.ACCUMULATION,
    )

    # Both warmup candidates share one WarmupStage (DYNAMIC), which only
    # ever yields one pick -- the pattern-matching one winning proves the
    # pattern-overlap filter ran, not just "something got picked" (a plain
    # name-sorted pick would pick "A warmup unrelated" instead).
    warmup_ids = [b.exercise_id for b in session.blocks if b.phase == TrainingPhase.WARMUP]
    assert warmup_ids == [warmup_match.id]

    # Cooldown is sized to len(main_patterns) (here: 1, just SQUAT), so with
    # only one slot to fill it's exactly the matching exercise, same as
    # before this feature existed.
    cooldown_ids = [b.exercise_id for b in session.blocks if b.phase == TrainingPhase.COOLDOWN]
    assert cooldown_ids == [cooldown_match.id]


@pytest.mark.asyncio
async def test_falls_back_to_full_pool_when_nothing_overlaps(db_session) -> None:
    user = _make_user()
    db_session.add(user)

    main = _make_exercise(name="AAA main squat", phase=TrainingPhase.MAIN)
    warmup_only = _make_exercise(
        name="Z warmup unrelated", phase=TrainingPhase.WARMUP, warmup_stage=WarmupStage.RAISE
    )

    exercises = {"main": main, "warmup_only": warmup_only}
    db_session.add_all(exercises.values())
    db_session.add(ExerciseTargetStat(exercise_id=main.id, target_stat=TargetStat.STRENGTH, order=0))
    await db_session.flush()

    PATTERNS_BY_NAME.clear()
    PATTERNS_BY_NAME[main.name] = [MovementPattern.SQUAT]
    PATTERNS_BY_NAME[warmup_only.name] = [MovementPattern.PULL]  # no overlap with MAIN

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    session = await service._build_training_session(
        session_type=DaySessionType.OFF_ICE, user=user, block_phase=BlockPhase.ACCUMULATION
    )

    warmup_blocks = [b for b in session.blocks if b.phase == TrainingPhase.WARMUP]
    # No overlap anywhere in the pool -> falls back to the (only) candidate,
    # not left empty.
    assert [b.exercise_id for b in warmup_blocks] == [warmup_only.id]


@pytest.mark.asyncio
async def test_movement_pattern_lives_in_the_real_table_too(db_session) -> None:
    """Sanity check against the actual ExerciseMovementPattern table (no
    repository fake) -- proves _movement_patterns_union/the preferred_patterns
    plumbing reads real rows, not just the fake used by the other two tests
    in this file."""
    user = _make_user()
    db_session.add(user)

    main = _make_exercise(name="AAA real main squat", phase=TrainingPhase.MAIN)
    warmup_match = _make_exercise(
        name="Z real warmup squat", phase=TrainingPhase.WARMUP, warmup_stage=WarmupStage.DYNAMIC
    )
    warmup_other = _make_exercise(
        name="A real warmup unrelated", phase=TrainingPhase.WARMUP, warmup_stage=WarmupStage.DYNAMIC
    )
    exercises = {"main": main, "warmup_match": warmup_match, "warmup_other": warmup_other}
    db_session.add_all(exercises.values())
    db_session.add(ExerciseTargetStat(exercise_id=main.id, target_stat=TargetStat.STRENGTH, order=0))
    db_session.add_all(
        [
            ExerciseMovementPattern(exercise_id=main.id, movement_pattern=MovementPattern.SQUAT),
            ExerciseMovementPattern(
                exercise_id=warmup_match.id, movement_pattern=MovementPattern.SQUAT
            ),
            ExerciseMovementPattern(exercise_id=warmup_other.id, movement_pattern=MovementPattern.PULL),
        ]
    )
    await db_session.flush()

    async def fake_list_for_assembly(
        *, phase, user, category=None, suitable_for_game_day=None
    ):
        pool = [e for e in exercises.values() if e.phase == phase]
        if category is not None:
            pool = [e for e in pool if e.category == category]
        return pool

    service = ScheduleService(db_session)
    service._exercises.list_for_assembly = fake_list_for_assembly
    # list_movement_patterns_by_exercise deliberately left real here.

    session = await service._build_training_session(
        session_type=DaySessionType.OFF_ICE, user=user, block_phase=BlockPhase.ACCUMULATION
    )

    # Same shared-stage shape as the fake-repository test above -- one slot,
    # the matching exercise wins it.
    warmup_blocks = [b for b in session.blocks if b.phase == TrainingPhase.WARMUP]
    assert [b.exercise_id for b in warmup_blocks] == [warmup_match.id]
