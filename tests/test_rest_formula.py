"""app.core.rest.rest_seconds_for -- pure-function boundary checks, no DB
needed. Same style as TestMaxDifficultyForLevel in test_level_difficulty_gate.py.
"""
import pytest

from app.core.rest import rest_seconds_for
from app.models.exercise import StimulusType


@pytest.mark.parametrize(
    ("stimulus_type", "difficulty_level", "expected_seconds"),
    [
        (StimulusType.STRENGTH, 1, 120),  # low end of the range at difficulty 1
        (StimulusType.STRENGTH, 5, 180),  # high end of the range at max difficulty
        (StimulusType.STRENGTH, 3, 150),  # midpoint difficulty -> midpoint rest
        (StimulusType.POWER, 1, 120),
        (StimulusType.POWER, 5, 180),
        (StimulusType.ENDURANCE, 1, 30),
        (StimulusType.ENDURANCE, 5, 60),
        (StimulusType.SKILL, 1, 60),
        (StimulusType.SKILL, 5, 90),
        (StimulusType.MOBILITY, 1, 15),
        (StimulusType.MOBILITY, 5, 30),
        (None, 3, None),  # unclassified exercise -> no suggestion, not a guess
    ],
)
def test_rest_seconds_for_stimulus_and_difficulty(
    stimulus_type: StimulusType | None, difficulty_level: int, expected_seconds: int | None
) -> None:
    assert rest_seconds_for(stimulus_type, difficulty_level) == expected_seconds
