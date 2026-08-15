"""Periodization: what biases exercise selection per BlockPhase, and the
pure decision rule for when a phase should advance (Phase 4 -- driven by
completed real sessions, not calendar weeks; see
TrainingBlockService.resolve_active_block for the DB-querying/mutating side
of this).
"""
from collections.abc import Callable

from app.models.exercise import Exercise
from app.models.schedule import BlockPhase

_INTENSIFICATION_DIFFICULTY_FLOOR = 4
_DELOAD_DIFFICULTY_CEILING = 2

MAX_DIFFICULTY_LEVEL = 5

# User.level -> highest Exercise.difficulty_level the assembly pipeline may
# pick. Ordered ascending on the threshold; the first row whose threshold is
# > level wins. Edit this list to retune the level gate -- nothing else in
# the assembly code needs to change.
_LEVEL_DIFFICULTY_CAPS: list[tuple[int, int]] = [
    (8, 2),  # level < 8  -> difficulty <= 2
    (15, 3),  # 8 <= level < 15 -> difficulty <= 3
]  # level >= 15 -> difficulty <= MAX_DIFFICULTY_LEVEL (no cap)


def max_difficulty_for_level(level: int) -> int:
    for threshold, cap in _LEVEL_DIFFICULTY_CAPS:
        if level < threshold:
            return cap
    return MAX_DIFFICULTY_LEVEL


MIN_DIFFICULTY_LEVEL = 1


def effective_difficulty_cap(level_cap: int, difficulty_throttle_steps: int) -> int:
    """Phase 5 structural brake: level_cap minus the user's current
    throttle (see app.core.overload.compute_difficulty_throttle_steps),
    floored at MIN_DIFFICULTY_LEVEL -- User.level/XP are never touched by
    this, only which exercises are eligible to be picked right now.
    """
    return max(MIN_DIFFICULTY_LEVEL, level_cap - difficulty_throttle_steps)


# Exercises a phase prefers, given a candidate pool for a single target_stat.
# Absent from this dict (accumulation) means "no difficulty preference at all".
DIFFICULTY_PRIORITY_PREDICATES: dict[BlockPhase, Callable[[Exercise], bool]] = {
    BlockPhase.INTENSIFICATION: lambda exercise: exercise.difficulty_level
    >= _INTENSIFICATION_DIFFICULTY_FLOOR,
    BlockPhase.DELOAD: lambda exercise: exercise.difficulty_level <= _DELOAD_DIFFICULTY_CEILING,
}

# (min, max) for random.randint when picking how many main-block exercises to
# assemble. Every phase has its own count now: accumulation is the
# volume-building phase (most exercises, shortest rest -- see
# app.core.rest), intensification trades some of that volume for heavier
# work (fewer exercises, longer rest between sets), deload cuts furthest
# (fewest exercises) to actually deload.
MAIN_EXERCISE_COUNT_RANGE: dict[BlockPhase, tuple[int, int]] = {
    BlockPhase.ACCUMULATION: (5, 6),
    BlockPhase.INTENSIFICATION: (4, 5),
    BlockPhase.DELOAD: (3, 4),
}

# Ordered mesocycle sequence -- DELOAD has no "next phase" (its completion
# rolls over to a brand-new TrainingBlock instead, handled by
# TrainingBlockService._advance).
_PHASE_ORDER: tuple[BlockPhase, ...] = (BlockPhase.ACCUMULATION, BlockPhase.INTENSIFICATION, BlockPhase.DELOAD)

# M in the spec: real (on/off-ice) sessions completed since phase_started_at
# that trigger an advance, for BOTH accumulation->intensification and
# intensification->deload. Chosen to roughly track
# MAIN_EXERCISE_COUNT_RANGE[ACCUMULATION]'s upper bound -- about a week to a
# week and a half of training at ordinary frequency.
SESSIONS_TO_ADVANCE_PHASE = 6

# N in the spec: soft calendar ceiling per phase, independent of session
# count -- purely a safety net so a fully inactive user doesn't stay parked
# in one phase forever. Applies uniformly to all three phases (including
# deload's roll to a new block), not just accumulation.
PHASE_CALENDAR_CEILING_WEEKS = 8


def next_phase(phase: BlockPhase) -> BlockPhase | None:
    """The phase after `phase` in a mesocycle, or None when `phase` is
    DELOAD -- its completion rolls over to a new TrainingBlock rather than
    to a "next phase" within this one.
    """
    index = _PHASE_ORDER.index(phase)
    if index + 1 >= len(_PHASE_ORDER):
        return None
    return _PHASE_ORDER[index + 1]


def phase_transition_due(*, sessions_completed_in_phase: int, weeks_since_phase_started: int) -> bool:
    """True once either M real sessions have completed since the phase
    started, or the phase has run longer than the calendar ceiling -- pure
    decision rule, no DB access, so it's unit-testable on its own (the
    DB-querying/mutating side lives in TrainingBlockService).
    """
    return (
        sessions_completed_in_phase >= SESSIONS_TO_ADVANCE_PHASE
        or weeks_since_phase_started >= PHASE_CALENDAR_CEILING_WEEKS
    )
