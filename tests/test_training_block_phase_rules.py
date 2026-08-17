"""app.core.training_block.next_phase / phase_transition_due /
is_macrocycle_deload_block / main_exercise_count_range /
is_tapering / is_final_taper_week -- pure decision-rule checks, no DB
needed. Same style as test_rest_formula.py.
"""
from datetime import date, timedelta

import pytest

from app.core.training_block import (
    MACROCYCLE_DELOAD_INTERVAL_BLOCKS,
    MAIN_EXERCISE_COUNT_RANGE,
    PHASE_CALENDAR_CEILING_WEEKS,
    SESSIONS_TO_ADVANCE_PHASE,
    TAPER_WINDOW_WEEKS,
    is_final_taper_week,
    is_macrocycle_deload_block,
    is_tapering,
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


# -- Phase: П.5 tournament taper --

_TODAY = date(2026, 3, 1)


@pytest.mark.parametrize(
    ("tournament_date", "expected"),
    [
        (None, False),
        (_TODAY + timedelta(days=TAPER_WINDOW_WEEKS * 7), False),  # exactly one day outside the window
        (_TODAY + timedelta(days=TAPER_WINDOW_WEEKS * 7 - 1), True),  # just inside the window
        (_TODAY + timedelta(days=7), True),  # inside the window, not the final week
        (_TODAY, True),  # tournament is today -- still tapering
        (_TODAY - timedelta(days=1), False),  # tournament already passed -- no retroactive taper
    ],
)
def test_is_tapering(tournament_date: date | None, expected: bool) -> None:
    assert TAPER_WINDOW_WEEKS == 3  # pins the parametrized cases above
    assert is_tapering(_TODAY, tournament_date) == expected


@pytest.mark.parametrize(
    ("tournament_date", "expected"),
    [
        (None, False),
        (_TODAY + timedelta(days=7), False),  # exactly one day outside the final week
        (_TODAY + timedelta(days=6), True),  # just inside the final week
        (_TODAY, True),  # tournament is today -- still the final week
        (_TODAY - timedelta(days=1), False),  # tournament already passed
        (_TODAY + timedelta(days=14), False),  # inside the taper window, but not the final week
    ],
)
def test_is_final_taper_week(tournament_date: date | None, expected: bool) -> None:
    assert is_final_taper_week(_TODAY, tournament_date) == expected


def test_final_taper_week_clamps_to_deload_regardless_of_season(db_session=None) -> None:
    # Even OFFSEASON (no season effect at all) must be overridden once the
    # final taper week is active -- proves taper takes priority over
    # season_period, not the other way around.
    for block_phase in (BlockPhase.ACCUMULATION, BlockPhase.INTENSIFICATION, BlockPhase.DELOAD):
        assert main_exercise_count_range(
            block_phase,
            category=ExerciseCategory.OFF_ICE,
            season_period=SeasonPeriod.OFFSEASON,
            is_tapering=True,
            is_final_taper_week=True,
        ) == (3, 4)


def test_early_taper_window_shifts_phase_and_beats_playoffs() -> None:
    # is_tapering=True (but not the final week) must win outright over
    # season_period=PLAYOFFS, which would otherwise clamp straight to
    # DELOAD -- taper overrides season entirely rather than combining.
    assert main_exercise_count_range(
        BlockPhase.ACCUMULATION,
        category=ExerciseCategory.OFF_ICE,
        season_period=SeasonPeriod.PLAYOFFS,
        is_tapering=True,
        is_final_taper_week=False,
    ) == (4, 5)


def test_taper_does_not_affect_on_ice() -> None:
    assert main_exercise_count_range(
        BlockPhase.ACCUMULATION,
        category=ExerciseCategory.ON_ICE,
        season_period=SeasonPeriod.OFFSEASON,
        is_tapering=True,
        is_final_taper_week=True,
    ) == (5, 6)


def test_no_taper_falls_back_to_season_period() -> None:
    # is_tapering=False (the default) must not change existing П.4 behavior.
    assert main_exercise_count_range(
        BlockPhase.ACCUMULATION, category=ExerciseCategory.OFF_ICE, season_period=SeasonPeriod.SEASON
    ) == (4, 5)
