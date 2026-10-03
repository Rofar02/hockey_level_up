"""app.core.rest.rest_seconds_for -- pure-function boundary checks, no DB
needed. Same style as TestMaxDifficultyForLevel in test_level_difficulty_gate.py.
"""
import pytest

from app.core.rest import rest_seconds_for
from app.models.exercise import StimulusType


@pytest.mark.parametrize(
    ("stimulus_type", "difficulty_level", "expected_seconds"),
    [
        (StimulusType.STRENGTH, 1, 120),  # low end of the range at difficulty 1
        (StimulusType.STRENGTH, 5, 180),  # high end of the range at max difficulty
        (StimulusType.STRENGTH, 3, 150),  # midpoint difficulty -> midpoint rest
        (StimulusType.POWER, 1, 120),
        (StimulusType.POWER, 5, 180),
        (StimulusType.ENDURANCE, 1, 30),
        (StimulusType.ENDURANCE, 5, 60),
        (StimulusType.SKILL, 1, 60),
        (StimulusType.SKILL, 5, 90),
        (StimulusType.MOBILITY, 1, 15),
        (StimulusType.MOBILITY, 5, 30),
        (None, 3, None),  # unclassified exercise -> no suggestion, not a guess
    ],
)
def test_rest_seconds_for_stimulus_and_difficulty(
    stimulus_type: StimulusType | None, difficulty_level: int, expected_seconds: int | None
) -> None:
    assert rest_seconds_for(stimulus_type, difficulty_level) == expected_seconds


# 2026-10-03 catalog check: phase and movement pattern refine the stimulus range.
from app.models.exercise import MovementPattern, TrainingPhase  # noqa: E402


@pytest.mark.parametrize(
    ("stimulus_type", "phase", "patterns", "difficulty_level", "expected_seconds"),
    [
        # warm-up / cool-down never rest longer than mobility work
        (StimulusType.STRENGTH, TrainingPhase.WARMUP, [MovementPattern.CORE], 1, 15),
        (StimulusType.SKILL, TrainingPhase.WARMUP, [MovementPattern.COORDINATION], 1, 15),
        (StimulusType.STRENGTH, TrainingPhase.COOLDOWN, [MovementPattern.SQUAT], 5, 30),
        # light MAIN strength: core / rotation / mobility only
        (StimulusType.STRENGTH, TrainingPhase.MAIN, [MovementPattern.CORE], 1, 45),
        (StimulusType.STRENGTH, TrainingPhase.MAIN, [MovementPattern.ROTATION], 5, 75),
        (StimulusType.STRENGTH, TrainingPhase.MAIN, [MovementPattern.ANKLE_MOBILITY], 3, 60),
        (StimulusType.STRENGTH, TrainingPhase.MAIN, [MovementPattern.CORE, MovementPattern.COORDINATION], 1, 45),
        # any heavy pattern keeps the full strength range
        (StimulusType.STRENGTH, TrainingPhase.MAIN, [MovementPattern.CORE, MovementPattern.SQUAT], 1, 120),
        (StimulusType.STRENGTH, TrainingPhase.MAIN, [MovementPattern.HIP_HINGE], 5, 180),
        # no pattern known -> plain stimulus range, as before
        (StimulusType.STRENGTH, TrainingPhase.MAIN, [], 1, 120),
        # power is never shortened, even for core-only movement
        (StimulusType.POWER, TrainingPhase.MAIN, [MovementPattern.CORE], 1, 120),
        # strength-tagged puck drill rests like skill work
        (StimulusType.STRENGTH, TrainingPhase.PUCK, [MovementPattern.STICK_HANDLING], 3, 75),
        (StimulusType.SKILL, TrainingPhase.PUCK, [MovementPattern.STICK_HANDLING], 1, 60),
    ],
)
def test_rest_seconds_refined_by_phase_and_pattern(
    stimulus_type, phase, patterns, difficulty_level, expected_seconds
) -> None:
    assert rest_seconds_for(stimulus_type, difficulty_level, phase, patterns) == expected_seconds


def test_exercise_read_uses_patterns_but_does_not_expose_them() -> None:
    import uuid

    from app.models.exercise import Exercise, ExerciseCategory
    from app.schemas.exercise import exercise_to_read

    exercise = Exercise(
        id=uuid.uuid4(),
        name="Планка",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        stimulus_type=StimulusType.STRENGTH,
        tracks_weight=False,
        suitable_for_game_day=False,
        admin_reviewed=False,
        is_archived=False,
    )
    read = exercise_to_read(exercise, [], [MovementPattern.CORE])
    assert read.rest_seconds == 45
    dumped = read.model_dump()
    assert dumped["rest_seconds"] == 45
    assert "movement_patterns" not in dumped
    assert exercise_to_read(exercise, []).rest_seconds == 120
