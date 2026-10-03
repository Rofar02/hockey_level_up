"""Rest-between-sets formula, computed on read (not a stored Exercise
column): driven by stimulus_type and difficulty_level, not by how many reps
the set happens to be written for -- strength/power work needs 2-3+ minutes
for the next set to be safe and effective regardless of rep count, while
endurance/mobility work recovers in under a minute. Supersedes the earlier
target_reps-tiered version (backlog "Промпт 68 (отдых между подходами)"),
which only ever produced a suggestion for the handful of exercises with
target_sets/target_reps already filled in -- stimulus_type/difficulty_level
are set on every exercise in the catalog now (see
scripts/backfill_exercise_metadata.py), so this covers all of it.
"""
from collections.abc import Collection

from app.core.training_block import MAX_DIFFICULTY_LEVEL
from app.models.exercise import MovementPattern, StimulusType, TrainingPhase

# (seconds at difficulty_level=1, seconds at difficulty_level=MAX_DIFFICULTY_LEVEL)
# per stimulus_type, interpolated linearly in between -- "higher difficulty
# -> a bit more rest" falls out of one rule instead of a separate step
# function tacked on for difficulty>=3.
_REST_RANGE_SECONDS: dict[StimulusType, tuple[int, int]] = {
    StimulusType.STRENGTH: (120, 180),
    StimulusType.POWER: (120, 180),
    StimulusType.ENDURANCE: (30, 60),
    StimulusType.SKILL: (60, 90),
    StimulusType.MOBILITY: (15, 30),
}


# 2026-10-03 catalog check: stimulus alone gave 2-3 min rest to work that
# doesn't need it --
#  * warm-up/cool-down items tagged strength/skill (Жук, Планка, balance
#    drills) -- a warm-up must not cool down between sets;
#  * MAIN "strength" whose movement is only core / rotation / mobility /
#    coordination (planks, Pallof, calf raises, external rotations) --
#    small-muscle and stability work recovers in about a minute;
#  * a "strength"-tagged puck drill -- stick work rests like skill work.
# Heavy compound strength (squat, hinge, push, pull, locomotion) and power
# keep their full 2-3 min.
_LIGHT_STRENGTH_PATTERNS = frozenset(
    {
        MovementPattern.CORE,
        MovementPattern.ROTATION,
        MovementPattern.COORDINATION,
        MovementPattern.HIP_MOBILITY,
        MovementPattern.ANKLE_MOBILITY,
        MovementPattern.WRIST_MOBILITY,
        MovementPattern.SHOULDER_MOBILITY,
    }
)
_LIGHT_STRENGTH_RANGE_SECONDS = (45, 75)


def _rest_range(
    stimulus_type: StimulusType,
    phase: TrainingPhase | None,
    movement_patterns: Collection[MovementPattern] | None,
) -> tuple[int, int]:
    if phase in (TrainingPhase.WARMUP, TrainingPhase.COOLDOWN):
        return _REST_RANGE_SECONDS[StimulusType.MOBILITY]
    if phase == TrainingPhase.PUCK and stimulus_type == StimulusType.STRENGTH:
        return _REST_RANGE_SECONDS[StimulusType.SKILL]
    if (
        stimulus_type == StimulusType.STRENGTH
        and movement_patterns
        and set(movement_patterns) <= _LIGHT_STRENGTH_PATTERNS
    ):
        return _LIGHT_STRENGTH_RANGE_SECONDS
    return _REST_RANGE_SECONDS[stimulus_type]


def rest_seconds_for(
    stimulus_type: StimulusType | None,
    difficulty_level: int,
    phase: TrainingPhase | None = None,
    movement_patterns: Collection[MovementPattern] | None = None,
) -> int | None:
    """None only when stimulus_type itself is unclassified -- difficulty_level
    is a required column, so that half of the formula never has a
    missing-data case the way stimulus_type still can (e.g. a brand-new
    catalog entry nobody has classified yet). phase / movement_patterns
    refine it (see _rest_range); without them it's the plain stimulus range.
    """
    if stimulus_type is None:
        return None
    low, high = _rest_range(stimulus_type, phase, movement_patterns)
    fraction = (difficulty_level - 1) / (MAX_DIFFICULTY_LEVEL - 1)
    return round(low + (high - low) * fraction)
