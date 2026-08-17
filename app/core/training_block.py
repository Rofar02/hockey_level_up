"""Periodization: what biases exercise selection per BlockPhase, and the
pure decision rule for when a phase should advance (Phase 4 -- driven by
completed real sessions, not calendar weeks; see
TrainingBlockService.resolve_active_block for the DB-querying/mutating side
of this).
"""
from collections.abc import Callable
from datetime import date

from app.models.exercise import Exercise, ExerciseCategory
from app.models.schedule import BlockPhase
from app.models.user import SeasonPeriod

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


# Phase: П.5 tournament taper. 3 weeks (the middle of the handoff's
# "2-4 weeks" range, same resolution style as MACROCYCLE_DELOAD_INTERVAL_
# BLOCKS' "3 or 4 mesocycles"). The final week of that window gets its own,
# sharper tier -- see main_exercise_count_range.
TAPER_WINDOW_WEEKS = 3
_TAPER_FINAL_WEEK_DAYS = 7


def is_tapering(today: date, tournament_date: date | None) -> bool:
    """True from TAPER_WINDOW_WEEKS out through the tournament date itself
    (inclusive) -- pure decision rule, no DB access. False once the date
    has passed (no retroactive tapering) or if none is set.
    """
    if tournament_date is None:
        return False
    days_until = (tournament_date - today).days
    return 0 <= days_until < TAPER_WINDOW_WEEKS * 7


def is_final_taper_week(today: date, tournament_date: date | None) -> bool:
    """True during the final week of the taper window -- the sharp
    volume-drop tier.
    """
    if tournament_date is None:
        return False
    days_until = (tournament_date - today).days
    return 0 <= days_until < _TAPER_FINAL_WEEK_DAYS


def main_exercise_count_range(
    block_phase: BlockPhase,
    *,
    category: ExerciseCategory,
    season_period: SeasonPeriod,
    is_tapering: bool = False,
    is_final_taper_week: bool = False,
) -> tuple[int, int]:
    """MAIN_EXERCISE_COUNT_RANGE, tightened for off-ice training during the
    two in-season periods (Phase: П.4) -- on-ice and offseason/preseason
    are always unaffected.

    Playoffs clamps to the DELOAD range outright, regardless of which
    phase the block is actually in -- short, high-intensity period, volume
    never exceeds what a deload week already allows.

    Season is milder: assembles as if one phase further along toward
    deload (accumulation borrows intensification's range, intensification
    borrows deload's) via the same next_phase sequence above -- deload has
    no next phase, so it stays at its own (already the floor).

    Tournament taper (Phase: П.5) overrides season_period outright when
    active, rather than combining with it -- the more specific, date-bound
    signal wins. Same two-tier shape as season/playoffs above, reused
    verbatim: the final taper week clamps to DELOAD's range, the earlier
    part of the window borrows the next phase's range.
    """
    if category != ExerciseCategory.OFF_ICE:
        return MAIN_EXERCISE_COUNT_RANGE[block_phase]
    if is_final_taper_week:
        return MAIN_EXERCISE_COUNT_RANGE[BlockPhase.DELOAD]
    if is_tapering:
        shifted_phase = next_phase(block_phase) or block_phase
        return MAIN_EXERCISE_COUNT_RANGE[shifted_phase]
    if season_period == SeasonPeriod.PLAYOFFS:
        return MAIN_EXERCISE_COUNT_RANGE[BlockPhase.DELOAD]
    if season_period == SeasonPeriod.SEASON:
        shifted_phase = next_phase(block_phase) or block_phase
        return MAIN_EXERCISE_COUNT_RANGE[shifted_phase]
    return MAIN_EXERCISE_COUNT_RANGE[block_phase]


# Phase: П.4 seasonal mode. Three tiers of strictness -- offseason/preseason
# behave exactly as before (no entry in either dict below), season shortens
# both phase-transition thresholds by ~1.5x, playoffs by 2x -- short,
# high-intensity, real games multiple times a week, so a full mesocycle
# (and thus its DELOAD phase, "разгрузочная неделя" in the product spec)
# recurs correspondingly more often.
_SESSIONS_TO_ADVANCE_PHASE_BY_SEASON: dict[SeasonPeriod, int] = {
    SeasonPeriod.SEASON: 4,
    SeasonPeriod.PLAYOFFS: 3,
}
_PHASE_CALENDAR_CEILING_WEEKS_BY_SEASON: dict[SeasonPeriod, int] = {
    SeasonPeriod.SEASON: 5,
    SeasonPeriod.PLAYOFFS: 4,
}


def phase_transition_due(
    *,
    sessions_completed_in_phase: int,
    weeks_since_phase_started: int,
    season_period: SeasonPeriod = SeasonPeriod.OFFSEASON,
) -> bool:
    """True once either M real sessions have completed since the phase
    started, or the phase has run longer than the calendar ceiling -- pure
    decision rule, no DB access, so it's unit-testable on its own (the
    DB-querying/mutating side lives in TrainingBlockService).
    """
    sessions_threshold = _SESSIONS_TO_ADVANCE_PHASE_BY_SEASON.get(season_period, SESSIONS_TO_ADVANCE_PHASE)
    weeks_threshold = _PHASE_CALENDAR_CEILING_WEEKS_BY_SEASON.get(season_period, PHASE_CALENDAR_CEILING_WEEKS)
    return (
        sessions_completed_in_phase >= sessions_threshold
        or weeks_since_phase_started >= weeks_threshold
    )


# Phase: П.2 macrocycle deload. Every Nth completed mesocycle (TrainingBlock
# rollover), the new block runs weight/reps suggestion at the floor of
# whatever range/history it would otherwise use, regardless of accumulated
# progress -- a full-block recovery period, distinct from the existing
# per-block DELOAD phase above. Fixed at one concrete number, same style as
# SESSIONS_TO_ADVANCE_PHASE/PHASE_CALENDAR_CEILING_WEEKS, rather than the
# "3 or 4" range the original design note left open -- picked the wider end
# to leave more room for real progress between recovery blocks.
MACROCYCLE_DELOAD_INTERVAL_BLOCKS = 4


def is_macrocycle_deload_block(block_number: int) -> bool:
    """Whether `block_number` is a scheduled recovery block. Pure decision
    rule, no DB access -- see TrainingBlockService._advance for where this
    is called at block-creation time.
    """
    return block_number % MACROCYCLE_DELOAD_INTERVAL_BLOCKS == 0
