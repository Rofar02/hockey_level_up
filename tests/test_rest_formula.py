"""app.core.rest.rest_seconds_for -- pure-function boundary checks, no DB
needed. Same style as TestMaxDifficultyForLevel in
test_level_difficulty_gate.py.
"""
import pytest

from app.core.rest import rest_seconds_for


@pytest.mark.parametrize(
    ("target_sets", "target_reps", "expected_seconds"),
    [
        (3, 1, 180),  # near-max single -> longest rest
        (3, 5, 180),  # boundary: reps<=5 -> still the low-rep tier
        (3, 6, 90),  # boundary: reps=6 -> the medium tier, not low
        (4, 12, 90),  # boundary: reps<=12 -> still the medium-rep tier
        (4, 13, 45),  # boundary: reps=13 -> the high-rep tier, not medium
        (3, 20, 45),  # deep into endurance rep ranges -> shortest rest
        (None, 10, None),  # no sets structure at all -> nothing to rest between
        (3, None, None),  # duration-based exercise, no rep count -> not covered
        (None, None, None),
    ],
)
def test_rest_seconds_for_tiers_and_boundaries(
    target_sets: int | None, target_reps: int | None, expected_seconds: int | None
) -> None:
    assert rest_seconds_for(target_sets, target_reps) == expected_seconds
