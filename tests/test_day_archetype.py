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
    PATTERN_ARCHETYPES,
    ROTATING_PATTERNS,
    ROTATION_SESSION_LIMIT,
    choose_archetype,
    forces_technical_archetype,
    initial_rotation_order,
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


def test_pattern_archetypes_gives_every_eligible_pattern_the_full_three_way_split() -> None:
    """2026-09-20 fix (round-4 audit): PUSH/PULL used to be narrowed to
    (STRENGTH, POWER) on the premise that the catalog had zero push/skill
    and pull/skill candidates (2026-09-17 fix, audit round 1 item #1).
    That premise stopped holding once the catalog gained real,
    correctly-tagged content for both -- with the narrower tuple,
    choose_archetype/initial_rotation_order could never resolve to SKILL
    for either pattern, making that real content permanently unreachable
    through the normal rotation. All four eligible patterns now share the
    same full three-way split."""
    for pattern in ARCHETYPE_ELIGIBLE_PATTERNS:
        assert PATTERN_ARCHETYPES[pattern] == DAY_ARCHETYPES


def test_choose_archetype_never_picks_outside_narrowed_candidates() -> None:
    """choose_archetype's own `candidates` narrowing still needs to work in
    isolation even though no current PATTERN_ARCHETYPES entry actually
    narrows anymore (see the test above) -- a synthetic two-way split
    exercises the same code path PUSH/PULL used to rely on."""
    narrowed_candidates = (StimulusType.STRENGTH, StimulusType.POWER)
    # Nothing has ever been chosen -- default-first still respects the
    # narrowed set instead of falling back to the global STRENGTH constant
    # blindly (it happens to coincide here, but the fallback-to-candidates[0]
    # path is what's under test).
    assert choose_archetype({}, narrowed_candidates) in narrowed_candidates
    # Skill has "history" in the dict but isn't part of the narrowed
    # candidates passed in -- choose_archetype must never surface it as a
    # result regardless.
    last_chosen_at = {
        StimulusType.STRENGTH: TODAY - timedelta(days=1),
        StimulusType.POWER: TODAY - timedelta(days=100),
        StimulusType.SKILL: None,
    }
    assert choose_archetype(last_chosen_at, narrowed_candidates) == StimulusType.POWER


def test_initial_rotation_order_respects_narrowed_candidates() -> None:
    narrowed_candidates = (StimulusType.STRENGTH, StimulusType.POWER)
    order = initial_rotation_order({}, narrowed_candidates)
    assert set(order) == set(narrowed_candidates)
    assert StimulusType.SKILL not in order


def test_rotating_patterns_are_the_four_non_archetype_patterns_with_enough_content() -> None:
    assert ROTATING_PATTERNS == {
        MovementPattern.LOCOMOTION,
        MovementPattern.CORE,
        MovementPattern.COORDINATION,
        MovementPattern.ROTATION,
    }
    # *_mobility and stick_handling are WARMUP content -- deliberately left
    # out of MAIN-block rotation scope.
    assert MovementPattern.STICK_HANDLING not in ROTATING_PATTERNS
    assert not any(p.value.endswith("_mobility") for p in ROTATING_PATTERNS)
    assert ROTATING_PATTERNS.isdisjoint(ARCHETYPE_ELIGIBLE_PATTERNS)


def test_rotation_session_limit_is_a_small_positive_number() -> None:
    assert 1 <= ROTATION_SESSION_LIMIT <= 6


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
