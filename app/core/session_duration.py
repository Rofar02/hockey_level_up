"""Honest session-duration estimate, replacing the static SESSION_TEMPLATES
percentages (app.core.session_templates, deleted) as the source of
TrainingSessionRead.phase_split. Each block's seconds are estimated from its
own exercise -- sets/reps blocks from target_sets/rep_range midpoint plus rest
between sets (app.core.rest), duration blocks from target_duration_seconds
directly -- and phase_split is the real proportion of a session's total
estimated seconds each phase accounts for, instead of a fixed 15/75/10 split
that had no relationship to what was actually assembled.
"""
from collections import defaultdict

from app.core.rest import rest_seconds_for
from app.models.exercise import Exercise, ExerciseType, TrainingPhase

# Rough tempo estimate for a single rep (lift + lower + brief pause) used
# only when an exercise doesn't already specify target_duration_seconds --
# not meant to be exact, just a reasonable, documented constant so the
# formula is honest about where its numbers come from.
SECONDS_PER_REP_ESTIMATE = 4

# Flat fallback for a block whose exercise hasn't been programmed with real
# numbers yet -- as of the Phase 1 metadata backfill, most of the catalog has
# stimulus_type/exercise_type classified but still has target_sets/
# rep_range_min/rep_range_max/target_duration_seconds left NULL (that's a
# separate, much larger "write actual set/rep/duration prescriptions for the
# whole catalog" task). Falling back to a flat estimate here keeps
# phase_split from dividing by zero or silently dropping unprogrammed
# blocks, at the cost of being a guess for exactly the exercises that don't
# have real numbers yet -- once those numbers exist, this estimate is used
# less and less.
_DEFAULT_BLOCK_SECONDS = 90


def estimate_block_duration_seconds(exercise: Exercise) -> int:
    if exercise.exercise_type == ExerciseType.DURATION:
        return exercise.target_duration_seconds or _DEFAULT_BLOCK_SECONDS

    if exercise.exercise_type == ExerciseType.SETS_REPS:
        if exercise.target_sets and exercise.rep_range_min and exercise.rep_range_max:
            rest = rest_seconds_for(exercise.stimulus_type, exercise.difficulty_level) or 0
            # Midpoint of the rep range (Phase: П.1 double progression) --
            # reps are now a [min, max] range per exercise, not a single
            # target, so there's no one "the" rep count to multiply by.
            avg_reps = (exercise.rep_range_min + exercise.rep_range_max) / 2
            work_seconds = exercise.target_sets * avg_reps * SECONDS_PER_REP_ESTIMATE
            rest_seconds_total = (exercise.target_sets - 1) * rest
            return round(work_seconds + rest_seconds_total)
        return _DEFAULT_BLOCK_SECONDS

    # exercise_type itself unclassified (nullable column, shouldn't happen
    # post-backfill but not enforced by a constraint) -- same flat fallback.
    return _DEFAULT_BLOCK_SECONDS


def estimate_session_duration_seconds(blocks: list[tuple[TrainingPhase, Exercise]]) -> int:
    """Total estimated seconds across every block, regardless of phase --
    a consequence of exercise selection, not a stated input, for every
    session_type.
    """
    return sum(estimate_block_duration_seconds(exercise) for _, exercise in blocks)


def compute_phase_split(blocks: list[tuple[TrainingPhase, Exercise]]) -> dict[TrainingPhase, float]:
    """Real proportion of estimated session time each phase accounts for.
    Only phases actually present among `blocks` show up in the result (a
    session with no cooldown block simply has no COOLDOWN key) -- callers
    already treat this as a partial mapping (see frontend's
    Partial<Record<TrainingPhase, number>>). Empty input (or, in principle,
    every block estimating to 0 seconds) returns an empty dict rather than
    dividing by zero.
    """
    by_phase: dict[TrainingPhase, int] = defaultdict(int)
    for phase, exercise in blocks:
        by_phase[phase] += estimate_block_duration_seconds(exercise)

    total = sum(by_phase.values())
    if total == 0:
        return {}
    return {phase: seconds / total for phase, seconds in by_phase.items()}
