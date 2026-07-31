"""Phase 9 periodization: block-phase from week_in_block, and how it biases
exercise selection (difficulty preference + main-block exercise count).
"""
import enum
from collections.abc import Callable

from app.models.exercise import Exercise

WEEKS_PER_BLOCK = 4

_INTENSIFICATION_DIFFICULTY_FLOOR = 4
_DELOAD_DIFFICULTY_CEILING = 2


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
# assemble. Deload is the only phase that changes the count, not just the
# selection within it.
MAIN_EXERCISE_COUNT_RANGE: dict[BlockPhase, tuple[int, int]] = {
    BlockPhase.ACCUMULATION: (2, 3),
    BlockPhase.INTENSIFICATION: (2, 3),
    BlockPhase.DELOAD: (1, 2),
}
