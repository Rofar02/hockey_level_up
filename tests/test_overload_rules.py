"""app.core.overload -- pure decision-rule checks, no DB needed. Same style
as test_rest_formula.py/test_training_block_phase_rules.py.
"""
import pytest

from app.core.overload import (
    STRUCTURAL_BRAKE_WINDOW,
    STRUCTURAL_RECOVERY_STREAK,
    SessionSignal,
    classify_session,
    compute_difficulty_throttle_steps,
    tactical_brake_engaged,
)

OVERLOAD = SessionSignal.OVERLOAD
OK = SessionSignal.OK


@pytest.mark.parametrize(
    ("hard_count", "max_count", "total_with_feedback", "expected"),
    [
        (0, 0, 3, OK),  # 0/3 hard+max -- comfortably fine
        (1, 0, 3, OK),  # 1/3 hard -> 0.333, under the 0.5 hard+max threshold
        (2, 0, 4, OVERLOAD),  # 2/4 hard -> exactly 0.5, boundary is inclusive
        (1, 1, 4, OVERLOAD),  # (1+1)/4 = 0.5 -> hard+max rule fires
    ],
)
def test_classify_session_hard_or_max_ratio(hard_count, max_count, total_with_feedback, expected) -> None:
    assert (
        classify_session(hard_count=hard_count, max_count=max_count, total_with_feedback=total_with_feedback)
        == expected
    )


def test_classify_session_below_minimum_feedback_is_excluded() -> None:
    assert classify_session(hard_count=3, max_count=0, total_with_feedback=2) is None


def test_classify_session_max_only_ratio_boundary() -> None:
    # 1/4 max, 0 hard -> (0+1)/4=0.25 hits the max-only threshold even
    # though hard+max ratio alone (also 0.25) wouldn't trip the 0.5 rule.
    assert classify_session(hard_count=0, max_count=1, total_with_feedback=4) == OVERLOAD
    # Just under the max-only boundary (1/5 = 0.2) and comfortably under
    # hard+max too -> ok.
    assert classify_session(hard_count=0, max_count=1, total_with_feedback=5) == OK


def test_classify_session_all_normal_feedback_is_ok() -> None:
    assert classify_session(hard_count=0, max_count=0, total_with_feedback=5) == OK


# -- tactical brake --


def test_tactical_brake_cold_start_never_engages() -> None:
    assert tactical_brake_engaged([]) is False
    assert tactical_brake_engaged([OVERLOAD]) is False


def test_tactical_brake_engages_on_two_overload_in_a_row() -> None:
    assert tactical_brake_engaged([OVERLOAD, OVERLOAD]) is True


def test_tactical_brake_does_not_engage_if_either_of_last_two_is_ok() -> None:
    assert tactical_brake_engaged([OK, OVERLOAD]) is False
    assert tactical_brake_engaged([OVERLOAD, OK]) is False


def test_tactical_brake_only_looks_at_the_two_most_recent() -> None:
    # Older overload history doesn't matter once the two most recent are ok.
    assert tactical_brake_engaged([OK, OK, OVERLOAD, OVERLOAD, OVERLOAD]) is False


# -- structural brake --


def test_structural_brake_cold_start_stays_at_zero() -> None:
    assert compute_difficulty_throttle_steps([OVERLOAD] * (STRUCTURAL_BRAKE_WINDOW - 1)) == 0


def test_structural_brake_pushes_one_step_on_three_of_five_overload() -> None:
    assert compute_difficulty_throttle_steps([OVERLOAD, OVERLOAD, OVERLOAD, OK, OK]) == 1


def test_structural_brake_does_not_push_below_threshold() -> None:
    assert compute_difficulty_throttle_steps([OVERLOAD, OVERLOAD, OK, OK, OK]) == 0


def test_structural_brake_push_is_edge_triggered_not_continuous() -> None:
    # 10 straight overload sessions: the "3 of trailing 5" condition becomes
    # true at session 5 and stays true through session 10, but only pushes
    # once (edge-triggered), not 6 times.
    assert compute_difficulty_throttle_steps([OVERLOAD] * 10) == 1


def test_structural_brake_recovers_one_step_per_two_consecutive_ok() -> None:
    history = [OVERLOAD, OVERLOAD, OVERLOAD, OK, OK]  # throttle -> 1
    history += [OK, OK]  # two more consecutive ok -> recovers to 0
    assert compute_difficulty_throttle_steps(history) == 0


def test_structural_brake_recovery_streak_resets_on_overload() -> None:
    # Push ends on an overload session (not ok) so the push itself doesn't
    # pre-load the recovery streak -- isolates "an overload in the middle
    # of an ok streak resets it" from the push/recovery interaction covered
    # by the other tests in this file.
    history = [OK, OK, OVERLOAD, OVERLOAD, OVERLOAD]  # push -> 1, streak stays 0
    history += [OK, OVERLOAD, OK]  # streak broken by the overload in between
    assert compute_difficulty_throttle_steps(history) == 1


def test_structural_brake_never_goes_negative() -> None:
    history = [OK] * 20
    assert compute_difficulty_throttle_steps(history) == 0


def test_structural_brake_rearms_after_a_full_recovery() -> None:
    # First episode pushes to 1; a long enough all-ok gap fully flushes the
    # trailing window of episode 1's overloads (recovering throttle back to
    # 0 well before the gap even ends), so a second, later bad episode is
    # free to register as a genuinely new rising edge and push again.
    episode_1 = [OVERLOAD] * STRUCTURAL_BRAKE_WINDOW
    gap = [OK] * STRUCTURAL_BRAKE_WINDOW
    episode_2 = [OVERLOAD] * STRUCTURAL_BRAKE_WINDOW
    assert compute_difficulty_throttle_steps(episode_1 + gap + episode_2) == 1


def test_structural_brake_a_two_session_gap_fully_cancels_a_single_push() -> None:
    # The narrowest possible gap (exactly STRUCTURAL_RECOVERY_STREAK ok's)
    # between two 5-overload runs still nets throttle=0 -- recovery from
    # the first push and the second run's own rising-edge detection end up
    # cancelling out for this specific gap length.
    episode_1 = [OVERLOAD] * STRUCTURAL_BRAKE_WINDOW
    gap = [OK] * STRUCTURAL_RECOVERY_STREAK
    episode_2 = [OVERLOAD] * STRUCTURAL_BRAKE_WINDOW
    assert compute_difficulty_throttle_steps(episode_1 + gap + episode_2) == 0
