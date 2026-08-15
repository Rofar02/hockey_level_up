"""app.core.training_block.next_phase / phase_transition_due -- pure
decision-rule checks, no DB needed. Same style as test_rest_formula.py.
"""
import pytest

from app.core.training_block import (
    PHASE_CALENDAR_CEILING_WEEKS,
    SESSIONS_TO_ADVANCE_PHASE,
    next_phase,
    phase_transition_due,
)
from app.models.schedule import BlockPhase


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
