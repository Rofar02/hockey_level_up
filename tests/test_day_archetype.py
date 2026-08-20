"""app.core.day_archetype.choose_archetype / forces_technical_archetype --
pure decision-rule checks, no DB needed. Same style as
test_training_block_phase_rules.py.
"""
from datetime import date, timedelta

import pytest

from app.core.day_archetype import (
    ARCHETYPE_ELIGIBLE_PATTERNS,
    DAY_ARCHETYPES,
    DEFAULT_FIRST_ARCHETYPE,
    choose_archetype,
    forces_technical_archetype,
)
from app.models.exercise import ExerciseCategory, MovementPattern, StimulusType
from app.models.schedule import BlockPhase
from app.models.user import SeasonPeriod

TODAY = date(2026, 8, 20)


def test_archetype_eligible_patterns_are_exactly_the_four_strength_patterns() -> None:
    assert ARCHETYPE_ELIGIBLE_PATTERNS == {
        MovementPattern.SQUAT,
        MovementPattern.HIP_HINGE,
        MovementPattern.PUSH,
        MovementPattern.PULL,
    }


def test_default_first_archetype_is_strength() -> None:
    assert DEFAULT_FIRST_ARCHETYPE == StimulusType.STRENGTH
    assert DEFAULT_FIRST_ARCHETYPE in DAY_ARCHETYPES


def test_no_history_at_all_starts_at_strength() -> None:
    assert choose_archetype({}) == StimulusType.STRENGTH
    assert choose_archetype(
        {StimulusType.STRENGTH: None, StimulusType.POWER: None, StimulusType.SKILL: None}
    ) == StimulusType.STRENGTH


def test_never_tried_archetype_beats_any_dated_one() -> None:
    """Strength and power both have real dates, skill has never been
    chosen -- skill wins outright regardless of how recent the dated
    ones are."""
    last_chosen_at = {
        StimulusType.STRENGTH: TODAY - timedelta(days=100),
        StimulusType.POWER: TODAY - timedelta(days=1),
        StimulusType.SKILL: None,
    }
    assert choose_archetype(last_chosen_at) == StimulusType.SKILL


def test_among_dated_archetypes_the_oldest_wins() -> None:
    last_chosen_at = {
        StimulusType.STRENGTH: TODAY - timedelta(days=5),
        StimulusType.POWER: TODAY - timedelta(days=30),
        StimulusType.SKILL: TODAY - timedelta(days=10),
    }
    assert choose_archetype(last_chosen_at) == StimulusType.POWER


def test_missing_key_is_treated_the_same_as_an_explicit_none() -> None:
    last_chosen_at = {StimulusType.STRENGTH: TODAY - timedelta(days=5)}
    assert choose_archetype(last_chosen_at) == StimulusType.POWER  # power/skill both absent, tie -> enum order


@pytest.mark.parametrize(
    ("block_phase", "season_period", "is_tapering", "is_final_taper_week", "expected"),
    [
        # Plain deload phase, no season/taper involvement -- forces it.
        (BlockPhase.DELOAD, SeasonPeriod.OFFSEASON, False, False, True),
        # Accumulation/intensification with nothing special -- never forces.
        (BlockPhase.ACCUMULATION, SeasonPeriod.OFFSEASON, False, False, False),
        (BlockPhase.INTENSIFICATION, SeasonPeriod.OFFSEASON, False, False, False),
        # Playoffs clamps every phase to deload's range -- forces regardless
        # of the underlying block_phase.
        (BlockPhase.ACCUMULATION, SeasonPeriod.PLAYOFFS, False, False, True),
        (BlockPhase.INTENSIFICATION, SeasonPeriod.PLAYOFFS, False, False, True),
        # Final taper week clamps to deload's range outright.
        (BlockPhase.ACCUMULATION, SeasonPeriod.OFFSEASON, True, True, True),
        # Season borrows the *next* phase's range, not necessarily deload's
        # -- accumulation -> intensification's range, not a force.
        (BlockPhase.ACCUMULATION, SeasonPeriod.SEASON, False, False, False),
        # ...but intensification's next phase IS deload, so season+
        # intensification does resolve to deload's range -- forces too.
        (BlockPhase.INTENSIFICATION, SeasonPeriod.SEASON, False, False, True),
        # Non-final taper window borrows the next phase the same way season
        # does -- same accumulation/intensification split.
        (BlockPhase.ACCUMULATION, SeasonPeriod.OFFSEASON, True, False, False),
        (BlockPhase.INTENSIFICATION, SeasonPeriod.OFFSEASON, True, False, True),
    ],
)
def test_forces_technical_archetype_matches_the_resolved_count_range(
    block_phase: BlockPhase,
    season_period: SeasonPeriod,
    is_tapering: bool,
    is_final_taper_week: bool,
    expected: bool,
) -> None:
    assert (
        forces_technical_archetype(
            block_phase,
            category=ExerciseCategory.OFF_ICE,
            season_period=season_period,
            is_tapering=is_tapering,
            is_final_taper_week=is_final_taper_week,
        )
        == expected
    )


def test_forces_technical_archetype_never_applies_to_on_ice() -> None:
    """on_ice's count range never clamps to deload via season/playoffs/
    taper (see main_exercise_count_range) -- only its own block_phase can
    make it True, and squat/hip_hinge/push/pull don't exist on_ice anyway
    (see the real-catalog check done before writing this system), so this
    is purely a boundary-consistency check, not a real code path."""
    assert (
        forces_technical_archetype(
            BlockPhase.DELOAD,
            category=ExerciseCategory.ON_ICE,
            season_period=SeasonPeriod.PLAYOFFS,
        )
        is True
    )
    assert (
        forces_technical_archetype(
            BlockPhase.ACCUMULATION,
            category=ExerciseCategory.ON_ICE,
            season_period=SeasonPeriod.PLAYOFFS,
        )
        is False
    )
