"""app.core.session_duration -- pure-function checks, no DB needed. Same
style as test_rest_formula.py.
"""
import uuid

import pytest

from app.core.session_duration import (
    SECONDS_PER_REP_ESTIMATE,
    compute_phase_split,
    estimate_block_duration_seconds,
    estimate_session_duration_seconds,
)

# Mirrors app.core.session_duration._DEFAULT_BLOCK_SECONDS -- not imported
# (private) so this asserts against the same literal a caller would see,
# same as test_rest_formula.py hardcoding its expected seconds.
_DEFAULT_BLOCK_SECONDS = 90
from app.models.exercise import (
    EquipmentType,
    Exercise,
    ExerciseCategory,
    ExerciseType,
    StimulusType,
    TrainingPhase,
)


def _make_exercise(
    *,
    exercise_type: ExerciseType | None,
    stimulus_type: StimulusType | None = StimulusType.STRENGTH,
    difficulty_level: int = 1,
    target_sets: int | None = None,
    rep_range_min: int | None = None,
    rep_range_max: int | None = None,
    target_duration_seconds: int | None = None,
) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"exercise-{uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=difficulty_level,
        equipment_type=EquipmentType.BODYWEIGHT,
        exercise_type=exercise_type,
        stimulus_type=stimulus_type,
        target_sets=target_sets,
        rep_range_min=rep_range_min,
        rep_range_max=rep_range_max,
        target_duration_seconds=target_duration_seconds,
    )


def test_duration_block_uses_target_duration_seconds_directly() -> None:
    exercise = _make_exercise(exercise_type=ExerciseType.DURATION, target_duration_seconds=45)
    assert estimate_block_duration_seconds(exercise) == 45


def test_duration_block_without_target_falls_back_to_default() -> None:
    exercise = _make_exercise(exercise_type=ExerciseType.DURATION, target_duration_seconds=None)
    assert estimate_block_duration_seconds(exercise) == _DEFAULT_BLOCK_SECONDS


def test_sets_reps_block_combines_work_and_rest() -> None:
    # difficulty_level=1, strength -> rest_seconds_for is the low end of its
    # range (120s, see test_rest_formula.py). avg_reps is the range midpoint
    # (Phase: П.1 double progression -- reps are a [min, max] range now).
    exercise = _make_exercise(
        exercise_type=ExerciseType.SETS_REPS,
        stimulus_type=StimulusType.STRENGTH,
        difficulty_level=1,
        target_sets=3,
        rep_range_min=8,
        rep_range_max=12,
    )
    avg_reps = (8 + 12) / 2
    work = 3 * avg_reps * SECONDS_PER_REP_ESTIMATE
    rest = 2 * 120
    assert estimate_block_duration_seconds(exercise) == round(work + rest)


def test_sets_reps_block_without_numbers_falls_back_to_default() -> None:
    exercise = _make_exercise(
        exercise_type=ExerciseType.SETS_REPS, target_sets=None, rep_range_min=None, rep_range_max=None
    )
    assert estimate_block_duration_seconds(exercise) == _DEFAULT_BLOCK_SECONDS


def test_unclassified_exercise_type_falls_back_to_default() -> None:
    exercise = _make_exercise(exercise_type=None)
    assert estimate_block_duration_seconds(exercise) == _DEFAULT_BLOCK_SECONDS


def test_compute_phase_split_is_proportional_to_estimated_seconds() -> None:
    warmup = _make_exercise(exercise_type=ExerciseType.DURATION, target_duration_seconds=100)
    main = _make_exercise(exercise_type=ExerciseType.DURATION, target_duration_seconds=300)
    cooldown = _make_exercise(exercise_type=ExerciseType.DURATION, target_duration_seconds=100)

    split = compute_phase_split(
        [
            (TrainingPhase.WARMUP, warmup),
            (TrainingPhase.MAIN, main),
            (TrainingPhase.COOLDOWN, cooldown),
        ]
    )

    assert split == pytest.approx(
        {TrainingPhase.WARMUP: 0.2, TrainingPhase.MAIN: 0.6, TrainingPhase.COOLDOWN: 0.2}
    )


def test_compute_phase_split_omits_phases_with_no_blocks() -> None:
    main = _make_exercise(exercise_type=ExerciseType.DURATION, target_duration_seconds=60)
    split = compute_phase_split([(TrainingPhase.MAIN, main)])
    assert set(split) == {TrainingPhase.MAIN}
    assert split[TrainingPhase.MAIN] == pytest.approx(1.0)


def test_compute_phase_split_empty_blocks_returns_empty_dict() -> None:
    assert compute_phase_split([]) == {}


def test_estimate_session_duration_seconds_sums_every_block_regardless_of_phase() -> None:
    warmup = _make_exercise(exercise_type=ExerciseType.DURATION, target_duration_seconds=100)
    main = _make_exercise(exercise_type=ExerciseType.DURATION, target_duration_seconds=300)
    cooldown = _make_exercise(exercise_type=ExerciseType.DURATION, target_duration_seconds=100)

    total = estimate_session_duration_seconds(
        [
            (TrainingPhase.WARMUP, warmup),
            (TrainingPhase.MAIN, main),
            (TrainingPhase.COOLDOWN, cooldown),
        ]
    )

    assert total == 500


def test_estimate_session_duration_seconds_empty_blocks_is_zero() -> None:
    assert estimate_session_duration_seconds([]) == 0
