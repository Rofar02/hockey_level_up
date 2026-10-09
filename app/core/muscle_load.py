"""Body-muscles map (2026-08-20 planning session): pure decay logic for
UserMuscleLoad, mirroring app.services.stat_service's grace-period-then-
exponential-decay shape but tuned for recovery, not detraining.

Key difference from stat decay, and why it matters for callers: a stat's
current_value is a permanent high-water mark -- get_effective_value only
ever *projects* a temporary dip on read, never mutates the stored peak, so
stat_consumer can always add fresh gain straight onto the stale
current_value with no ill effect (last_updated_at resets, decay starts
counting from zero again). Muscle load has no "peak" worth preserving: a
muscle that was hammered Monday and left alone until Friday has, in
reality, already recovered by Friday, and a new session's load needs to
stack onto that *recovered* state, not onto Monday's still-fresh-looking
stored value. So muscle_load_consumer (app/events/handlers/block_completed.py)
collapses get_effective_muscle_load into the new current_value before
adding this session's contribution, rather than treating decay as a
read-only projection the way stat_service does. The read endpoint
(ProgressService) still calls get_effective_muscle_load too, for the same
reason stat reads do: decay keeps advancing between writes, a GET between
two workouts must reflect that even though nothing was written since.
"""
from datetime import datetime

from app.models.exercise import MuscleGroup
from app.models.progress import UserMuscleLoad
from app.models.schedule import DaySessionType
from app.models.training_diary import IceEffort

# Immediate post-training fatigue window: load stays at whatever
# muscle_load_consumer just set it to, no recovery credited yet. Short on
# purpose -- this is a 48-72h *muscle recovery* window overall (per this
# feature's own planning doc), not stat_service's multi-day "did you skip
# training" grace period, so it only needs to cover the first few hours of
# genuinely peak, not-yet-recovering soreness.
GRACE_PERIOD_HOURS = 12.0

# After the grace period, current_value halves every this many hours --
# tuned so the overall grace+decay window lands in the doc's 48-72h
# recovery target: at 48h idle (12h grace + 3 half-lives), ~12% of the
# original load remains; at 72h idle (12h grace + 5 half-lives), ~3%
# remains. Checked 2026-08-20 against ACSM's own 48-72h between-session
# recovery guidance (48h minimum, "better perceptual responses... at
# 72h") -- close enough to that real-world consensus that no retune was
# needed. Not validated against real dogfooding data yet (no
# UserMuscleLoad history existed when this was first written) -- revisit
# once real usage exists, same "initial estimate" honesty as other fresh
# constants in this codebase.
HALF_LIFE_HOURS = 12.0

# Unlike FLOOR_RATIO in stat_service (stats always retain 10% of peak),
# full recovery to 0 is the whole point here -- no floor.
MAX_INTENSITY = 10.0

# muscle_load_consumer's gain formula: difficulty_level (1-5) * this *
# the exercise's own ExerciseMuscleGroup weight (0-1) for that muscle. A
# single difficulty-5, full-weight exercise alone lands mid-range (4.0,
# "средняя") -- two or three same-muscle exercises in one session (the
# common case) stack into "перегружена" (9-10), matching the doc's "нужен
# отдых" framing for a real training day, not a single set. Not tuned
# against real UserMuscleLoad history yet (none exists at the time this
# was written) -- same "initial estimate" caveat as the decay constants
# above.
GAIN_PER_DIFFICULTY_LEVEL = 0.8


def get_idle_hours(load: UserMuscleLoad, now: datetime) -> float:
    # now must be tz-aware (e.g. datetime.now(timezone.utc)) to match
    # last_updated_at, which is stored tz-aware -- same contract as
    # stat_service.get_idle_days.
    return (now - load.last_updated_at).total_seconds() / 3600


def is_decay_active(idle_hours: float) -> bool:
    return idle_hours > GRACE_PERIOD_HOURS


def get_effective_muscle_load(load: UserMuscleLoad, now: datetime) -> float:
    idle_hours = get_idle_hours(load, now)
    if not is_decay_active(idle_hours):
        return load.current_value

    decay_hours = idle_hours - GRACE_PERIOD_HOURS
    half_lives_elapsed = decay_hours / HALF_LIFE_HOURS
    return load.current_value * (0.5**half_lives_elapsed)


# -- Ice and games on the muscle map (2026-10-09, release plan step 4) --

# Load of 60 minutes of medium ice, in the same units as an exercise block
# (difficulty x GAIN_PER_DIFFICULTY_LEVEL x weight). Skating loads the
# hips and thighs most, then the back and core holding the stance.
ICE_SESSION_DOSE: dict[MuscleGroup, float] = {
    MuscleGroup.GLUTES: 4.5,
    MuscleGroup.QUADS: 4.5,
    MuscleGroup.ADDUCTORS: 4.0,
    MuscleGroup.HIP_FLEXORS: 3.0,
    MuscleGroup.BACK: 3.0,
    MuscleGroup.CORE: 2.5,
    MuscleGroup.HAMSTRINGS: 2.0,
    MuscleGroup.CALVES: 1.5,
    MuscleGroup.SHOULDERS: 1.0,
    MuscleGroup.FOREARMS: 1.0,
}
ICE_REFERENCE_MINUTES = 60
ICE_MAX_DURATION_FACTOR = 1.5
ICE_EFFORT_FACTOR: dict[IceEffort, float] = {
    IceEffort.EASY: 0.6,
    IceEffort.NORMAL: 1.0,
    IceEffort.HARD: 1.4,
}
# A game is harder than practice; its report has no length or effort, so
# it is always counted as 60 medium minutes times this.
GAME_FACTOR = 1.3


def ice_load_scale(session_type: DaySessionType, minutes: int | None, effort: IceEffort | None) -> float:
    """How many "60 medium minutes of ice" a day was; no answer = 60 medium."""
    if session_type == DaySessionType.GAME:
        return GAME_FACTOR
    duration = min((minutes or ICE_REFERENCE_MINUTES) / ICE_REFERENCE_MINUTES, ICE_MAX_DURATION_FACTOR)
    return duration * ICE_EFFORT_FACTOR[effort or IceEffort.NORMAL]


def recovery_factor(hours_since: float) -> float:
    """The part of a load still left after this many hours -- the same
    grace-then-halving curve as get_effective_muscle_load, so a report sent
    the next day doesn't put yesterday's skating on as if it were fresh."""
    if hours_since <= GRACE_PERIOD_HOURS:
        return 1.0
    return 0.5 ** ((hours_since - GRACE_PERIOD_HOURS) / HALF_LIFE_HOURS)
