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
from app.core.training_block import MAX_DIFFICULTY_LEVEL
from app.models.exercise import StimulusType

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


def rest_seconds_for(stimulus_type: StimulusType | None, difficulty_level: int) -> int | None:
    """None only when stimulus_type itself is unclassified -- difficulty_level
    is a required column, so that half of the formula never has a
    missing-data case the way stimulus_type still can (e.g. a brand-new
    catalog entry nobody has classified yet).
    """
    if stimulus_type is None:
        return None
    low, high = _REST_RANGE_SECONDS[stimulus_type]
    fraction = (difficulty_level - 1) / (MAX_DIFFICULTY_LEVEL - 1)
    return round(low + (high - low) * fraction)
