"""Phase 9 periodization: block-phase from week_in_block, and how it biases
exercise selection (difficulty preference + main-block exercise count).
"""
import enum
from collections.abc import Callable

from app.models.exercise import Exercise

WEEKS_PER_BLOCK = 4

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


class BlockPhase(enum.StrEnum):
    ACCUMULATION = "accumulation"
    INTENSIFICATION = "intensification"
    DELOAD = "deload"


def get_phase(week_in_block: int) -> BlockPhase:
    if week_in_block in (1, 2):
        return BlockPhase.ACCUMULATION
    if week_in_block == 3:
        return BlockPhase.INTENSIFICATION
    if week_in_block == WEEKS_PER_BLOCK:
        return BlockPhase.DELOAD
    raise ValueError(f"week_in_block must be 1-4, got {week_in_block}")


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
