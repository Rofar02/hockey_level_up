"""app.core.training_block.next_phase / phase_transition_due /
is_macrocycle_deload_block / main_exercise_count_range -- pure
decision-rule checks, no DB needed. Same style as test_rest_formula.py.
"""
import pytest

from app.core.training_block import (
    MACROCYCLE_DELOAD_INTERVAL_BLOCKS,
    MAIN_EXERCISE_COUNT_RANGE,
    PHASE_CALENDAR_CEILING_WEEKS,
    SESSIONS_TO_ADVANCE_PHASE,
    is_macrocycle_deload_block,
    main_exercise_count_range,
    next_phase,
    phase_transition_due,
)
from app.models.exercise import ExerciseCategory
from app.models.schedule import BlockPhase
from app.models.user import SeasonPeriod


@pytest.mark.parametrize(
    ("phase", "expected"),
    [
        (BlockPhase.ACCUMULATION, BlockPhase.INTENSIFICATION),
        (BlockPhase.INTENSIFICATION, BlockPhase.DELOAD),
        (BlockPhase.DELOAD, None),  # rolls to a new TrainingBlock instead
    ],
)
def test_next_phase(phase: BlockPhase, expected: BlockPhase | None) -> None:
    assert next_phase(phase) == expected


@pytest.mark.parametrize(
    ("sessions_completed_in_phase", "weeks_since_phase_started", "expected"),
    [
        (0, 0, False),
        (SESSIONS_TO_ADVANCE_PHASE - 1, 0, False),  # one short -> not due
        (SESSIONS_TO_ADVANCE_PHASE, 0, True),  # session threshold alone triggers it
        (SESSIONS_TO_ADVANCE_PHASE + 5, 0, True),  # comfortably over, still True
        (0, PHASE_CALENDAR_CEILING_WEEKS - 1, False),  # one week short of the ceiling
        (0, PHASE_CALENDAR_CEILING_WEEKS, True),  # calendar ceiling alone triggers it
        (0, PHASE_CALENDAR_CEILING_WEEKS + 10, True),
    ],
)
def test_phase_transition_due(
    sessions_completed_in_phase: int, weeks_since_phase_started: int, expected: bool
) -> None:
    assert (
        phase_transition_due(
            sessions_completed_in_phase=sessions_completed_in_phase,
            weeks_since_phase_started=weeks_since_phase_started,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("block_number", "expected"),
    [
        (1, False),
        (2, False),
        (3, False),
        (4, True),
        (5, False),
        (6, False),
        (7, False),
        (8, True),
        (12, True),
    ],
)
def test_is_macrocycle_deload_block(block_number: int, expected: bool) -> None:
    assert MACROCYCLE_DELOAD_INTERVAL_BLOCKS == 4  # pins the parametrized cases above
    assert is_macrocycle_deload_block(block_number) == expected


# -- Phase: П.4 seasonal mode --


@pytest.mark.parametrize(
    ("sessions_completed_in_phase", "weeks_since_phase_started", "expected"),
    [
        (2, 0, False),  # one short of playoffs' 3 -> not due
        (3, 0, True),  # playoffs' own (lower) session threshold
        (0, 3, False),  # one week short of playoffs' 4-week ceiling
        (0, 4, True),  # playoffs' own (lower) calendar ceiling
        # Well under the normal (offseason) thresholds -- proves playoffs
        # isn't just reusing SESSIONS_TO_ADVANCE_PHASE/PHASE_CALENDAR_CEILING_WEEKS.
        (SESSIONS_TO_ADVANCE_PHASE - 1, PHASE_CALENDAR_CEILING_WEEKS - 1, True),
    ],
)
def test_phase_transition_due_playoffs(
    sessions_completed_in_phase: int, weeks_since_phase_started: int, expected: bool
) -> None:
    assert (
        phase_transition_due(
            sessions_completed_in_phase=sessions_completed_in_phase,
            weeks_since_phase_started=weeks_since_phase_started,
            season_period=SeasonPeriod.PLAYOFFS,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("sessions_completed_in_phase", "weeks_since_phase_started", "expected"),
    [
        (3, 0, False),  # one short of season's 4 -> not due
        (4, 0, True),  # season's own threshold
        (0, 4, False),  # one week short of season's 5-week ceiling
        (0, 5, True),  # season's own calendar ceiling
    ],
)
def test_phase_transition_due_season(
    sessions_completed_in_phase: int, weeks_since_phase_started: int, expected: bool
) -> None:
    assert (
        phase_transition_due(
            sessions_completed_in_phase=sessions_completed_in_phase,
            weeks_since_phase_started=weeks_since_phase_started,
            season_period=SeasonPeriod.SEASON,
        )
        == expected
    )


@pytest.mark.parametrize("season_period", [SeasonPeriod.OFFSEASON, SeasonPeriod.PRESEASON])
def test_phase_transition_due_offseason_preseason_use_normal_thresholds(
    season_period: SeasonPeriod,
) -> None:
    # season's/playoffs' lower thresholds must NOT apply here.
    assert (
        phase_transition_due(
            sessions_completed_in_phase=4,
            weeks_since_phase_started=0,
            season_period=season_period,
        )
        is False
    )
    assert (
        phase_transition_due(
            sessions_completed_in_phase=SESSIONS_TO_ADVANCE_PHASE,
            weeks_since_phase_started=0,
            season_period=season_period,
        )
        is True
    )


@pytest.mark.parametrize(
    ("block_phase", "category", "season_period", "expected"),
    [
        # Playoffs, off-ice -- clamped to DELOAD's range regardless of phase.
        (BlockPhase.ACCUMULATION, ExerciseCategory.OFF_ICE, SeasonPeriod.PLAYOFFS, (3, 4)),
        (BlockPhase.INTENSIFICATION, ExerciseCategory.OFF_ICE, SeasonPeriod.PLAYOFFS, (3, 4)),
        (BlockPhase.DELOAD, ExerciseCategory.OFF_ICE, SeasonPeriod.PLAYOFFS, (3, 4)),
        # Playoffs, on-ice -- never affected.
        (BlockPhase.ACCUMULATION, ExerciseCategory.ON_ICE, SeasonPeriod.PLAYOFFS, (5, 6)),
        # Season, off-ice -- shifted one phase toward deload.
        (BlockPhase.ACCUMULATION, ExerciseCategory.OFF_ICE, SeasonPeriod.SEASON, (4, 5)),
        (BlockPhase.INTENSIFICATION, ExerciseCategory.OFF_ICE, SeasonPeriod.SEASON, (3, 4)),
        (BlockPhase.DELOAD, ExerciseCategory.OFF_ICE, SeasonPeriod.SEASON, (3, 4)),  # already the floor
        # Season, on-ice -- never affected.
        (BlockPhase.ACCUMULATION, ExerciseCategory.ON_ICE, SeasonPeriod.SEASON, (5, 6)),
        # Offseason/preseason, off-ice -- normal range, unaffected.
        (BlockPhase.ACCUMULATION, ExerciseCategory.OFF_ICE, SeasonPeriod.OFFSEASON, (5, 6)),
        (BlockPhase.ACCUMULATION, ExerciseCategory.OFF_ICE, SeasonPeriod.PRESEASON, (5, 6)),
    ],
)
def test_main_exercise_count_range(
    block_phase: BlockPhase,
    category: ExerciseCategory,
    season_period: SeasonPeriod,
    expected: tuple[int, int],
) -> None:
    assert MAIN_EXERCISE_COUNT_RANGE[BlockPhase.ACCUMULATION] == (5, 6)  # pins the cases above
    assert main_exercise_count_range(block_phase, category=category, season_period=season_period) == expected
