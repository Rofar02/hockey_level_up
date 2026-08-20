"""Stage 2.5 (2026-08-20 planning session): warmup/cooldown's "what should
this target" signal is muscle groups MAIN actually loaded
(preferred_muscle_groups), not movement_pattern overlap -- see
ScheduleService._pick_sequence/_pick_warmup_complex's own docstrings for
why movement_pattern is kept as a fallback rather than dropped (zero real
ExerciseMuscleGroup rows exist yet, Stage 2.1 shipped the taxonomy the same
night as this, retagging is Stage 4's job). See
test_schedule_service_warmup_pattern_match.py for the pattern-only
behavior this builds on.

Real ExerciseMuscleGroup/ExerciseMovementPattern rows throughout (no
repository fake for either), same "lives in the real table" style as that
file's third test -- only list_for_assembly is faked, to keep the real
seeded catalog from leaking into these pools.
"""
import random
import uuid

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseMuscleGroup,
    ExerciseTargetStat,
    MovementPattern,
    MuscleGroup,
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
        username=f"warmup_muscle_{unique}",
        email=f"warmup_muscle_{unique}@example.com",
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
    async def fake_list_for_assembly(*, phase, user, category=None, suitable_for_game_day=None):
        pool = [e for e in exercises.values() if e.phase == phase]
        if category is not None:
            pool = [e for e in pool if e.category == category]
        return pool

    service._exercises.list_for_assembly = fake_list_for_assembly


@pytest.mark.asyncio
async def test_muscle_match_wins_over_pattern_match_when_they_disagree(db_session) -> None:
    """MAIN loads CHEST via a SQUAT-patterned exercise (deliberately
    mismatched, so pattern-matching and muscle-matching point at two
    different warmup candidates). The muscle-matching one must win the
    (single) DYNAMIC stage slot -- proves muscle groups are checked
    first, not just checked at all."""
    user = _make_user()
    db_session.add(user)

    main = _make_exercise(name="AAA main chest press", phase=TrainingPhase.MAIN)
    muscle_match = _make_exercise(
        name="Z warmup chest activation", phase=TrainingPhase.WARMUP, warmup_stage=WarmupStage.DYNAMIC
    )
    pattern_match = _make_exercise(
        name="A warmup squat mobility", phase=TrainingPhase.WARMUP, warmup_stage=WarmupStage.DYNAMIC
    )
    # Same disagreement, mirrored for cooldown (_pick_sequence -- a
    # separate implementation from _pick_warmup_complex, so this needs its
    # own proof the same fallback chain actually landed there too).
    cooldown_muscle_match = _make_exercise(name="Z cooldown chest stretch", phase=TrainingPhase.COOLDOWN)
    cooldown_pattern_match = _make_exercise(name="A cooldown squat stretch", phase=TrainingPhase.COOLDOWN)

    exercises = {
        "main": main,
        "muscle_match": muscle_match,
        "pattern_match": pattern_match,
        "cooldown_muscle_match": cooldown_muscle_match,
        "cooldown_pattern_match": cooldown_pattern_match,
    }
    db_session.add_all(exercises.values())
    db_session.add(ExerciseTargetStat(exercise_id=main.id, target_stat=TargetStat.STRENGTH, order=0))
    db_session.add_all([
        ExerciseMovementPattern(exercise_id=main.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=pattern_match.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=muscle_match.id, movement_pattern=MovementPattern.PULL),
        ExerciseMovementPattern(exercise_id=cooldown_pattern_match.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=cooldown_muscle_match.id, movement_pattern=MovementPattern.PULL),
        ExerciseMuscleGroup(exercise_id=main.id, muscle_group=MuscleGroup.CHEST, weight=1.0),
        ExerciseMuscleGroup(exercise_id=muscle_match.id, muscle_group=MuscleGroup.CHEST, weight=1.0),
        ExerciseMuscleGroup(exercise_id=pattern_match.id, muscle_group=MuscleGroup.QUADS, weight=1.0),
        ExerciseMuscleGroup(exercise_id=cooldown_muscle_match.id, muscle_group=MuscleGroup.CHEST, weight=1.0),
        ExerciseMuscleGroup(exercise_id=cooldown_pattern_match.id, muscle_group=MuscleGroup.QUADS, weight=1.0),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    session = await service._build_training_session(
        session_type=DaySessionType.OFF_ICE, user=user, block_phase=BlockPhase.ACCUMULATION
    )

    warmup_ids = [b.exercise_id for b in session.blocks if b.phase == TrainingPhase.WARMUP]
    assert warmup_ids == [muscle_match.id]

    # Cooldown is sized to len(main_patterns) (here: 1, just SQUAT), so
    # with one slot to fill, the muscle-matching candidate must win it.
    cooldown_ids = [b.exercise_id for b in session.blocks if b.phase == TrainingPhase.COOLDOWN]
    assert cooldown_ids == [cooldown_muscle_match.id]


@pytest.mark.asyncio
async def test_falls_back_to_pattern_match_when_no_muscle_group_data(db_session) -> None:
    """Today's real catalog state: zero ExerciseMuscleGroup rows anywhere.
    With no muscle-group data on any candidate, matching must fall back to
    movement_pattern -- identical outcome to the pre-Stage-2.5 behavior,
    not an empty/random result."""
    user = _make_user()
    db_session.add(user)

    main = _make_exercise(name="AAA main squat", phase=TrainingPhase.MAIN)
    pattern_match = _make_exercise(
        name="Z warmup squat mobility", phase=TrainingPhase.WARMUP, warmup_stage=WarmupStage.DYNAMIC
    )
    unrelated = _make_exercise(
        name="A warmup unrelated", phase=TrainingPhase.WARMUP, warmup_stage=WarmupStage.DYNAMIC
    )

    exercises = {"main": main, "pattern_match": pattern_match, "unrelated": unrelated}
    db_session.add_all(exercises.values())
    db_session.add(ExerciseTargetStat(exercise_id=main.id, target_stat=TargetStat.STRENGTH, order=0))
    db_session.add_all([
        ExerciseMovementPattern(exercise_id=main.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=pattern_match.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=unrelated.id, movement_pattern=MovementPattern.PULL),
    ])
    # No ExerciseMuscleGroup rows at all -- matches the real catalog today.
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    session = await service._build_training_session(
        session_type=DaySessionType.OFF_ICE, user=user, block_phase=BlockPhase.ACCUMULATION
    )

    warmup_ids = [b.exercise_id for b in session.blocks if b.phase == TrainingPhase.WARMUP]
    assert warmup_ids == [pattern_match.id]


@pytest.mark.asyncio
async def test_falls_back_to_full_pool_when_neither_matches(db_session) -> None:
    user = _make_user()
    db_session.add(user)

    main = _make_exercise(name="AAA main squat", phase=TrainingPhase.MAIN)
    warmup_only = _make_exercise(
        name="Z warmup unrelated", phase=TrainingPhase.WARMUP, warmup_stage=WarmupStage.RAISE
    )

    exercises = {"main": main, "warmup_only": warmup_only}
    db_session.add_all(exercises.values())
    db_session.add(ExerciseTargetStat(exercise_id=main.id, target_stat=TargetStat.STRENGTH, order=0))
    db_session.add_all([
        ExerciseMovementPattern(exercise_id=main.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=warmup_only.id, movement_pattern=MovementPattern.PULL),
        ExerciseMuscleGroup(exercise_id=main.id, muscle_group=MuscleGroup.QUADS, weight=1.0),
        ExerciseMuscleGroup(exercise_id=warmup_only.id, muscle_group=MuscleGroup.CHEST, weight=1.0),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    session = await service._build_training_session(
        session_type=DaySessionType.OFF_ICE, user=user, block_phase=BlockPhase.ACCUMULATION
    )

    warmup_blocks = [b for b in session.blocks if b.phase == TrainingPhase.WARMUP]
    assert [b.exercise_id for b in warmup_blocks] == [warmup_only.id]
