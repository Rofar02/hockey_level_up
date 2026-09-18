"""2026-09-18 audit round 2 item #1: ScheduleService._tier_by_escalated_difficulty,
the pure tiering rule behind bodyweight-escalation's "at a true difficulty
ceiling, swap sideways instead of downgrading" fix. Pure function, no DB --
constructed Exercise rows are never added to a session.
"""
import uuid

from app.models.exercise import Exercise, ExerciseCategory, ExerciseType, TrainingPhase
from app.services.schedule_service import ScheduleService


def _exercise(name: str, *, difficulty_level: int) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=difficulty_level,
        exercise_type=ExerciseType.SETS_REPS,
        rep_range_min=8,
        rep_range_max=12,
        tracks_weight=False,
    )


def test_prefers_strictly_higher_difficulty_when_available() -> None:
    outgoing = _exercise("Push-up", difficulty_level=2)
    same = _exercise("Diamond push-up", difficulty_level=2)
    higher = _exercise("Archer push-up", difficulty_level=3)

    result = ScheduleService._tier_by_escalated_difficulty([outgoing, same, higher], outgoing)

    assert result == [higher]


def test_falls_back_to_a_different_same_difficulty_variant_at_a_true_ceiling() -> None:
    """No candidate above `outgoing`'s own difficulty -- a real ceiling for
    this pattern -- so the fix should pick a *different* exercise at the
    same level rather than degrading to an unconstrained/lower pick."""
    outgoing = _exercise("Push-up", difficulty_level=2)
    same = _exercise("Diamond push-up", difficulty_level=2)
    lower = _exercise("Knee push-up", difficulty_level=1)

    result = ScheduleService._tier_by_escalated_difficulty([outgoing, same, lower], outgoing)

    assert result == [same]


def test_never_returns_the_outgoing_exercise_in_the_same_difficulty_tier() -> None:
    """Defensive against an upstream caller that failed to exclude
    `outgoing` from `pool` itself -- the same-difficulty tier must exclude
    it explicitly, not rely on the caller having already done so."""
    outgoing = _exercise("Push-up", difficulty_level=2)
    same = _exercise("Diamond push-up", difficulty_level=2)

    result = ScheduleService._tier_by_escalated_difficulty([outgoing, same], outgoing)

    assert outgoing not in result
    assert result == [same]


def test_last_resort_returns_outgoing_when_nothing_else_exists() -> None:
    """The boundary case: no higher difficulty AND no other same-difficulty
    variant either (a genuine catalog gap, or `outgoing` is the only
    candidate at all) -- must still return something, not an empty list,
    so a caller never has to special-case "no slot"."""
    outgoing = _exercise("Push-up", difficulty_level=2)

    result = ScheduleService._tier_by_escalated_difficulty([outgoing], outgoing)

    assert result == [outgoing]


def test_last_resort_falls_back_to_lower_difficulty_pool_when_present() -> None:
    """Same boundary case, but the pool isn't literally empty -- only
    lower-difficulty alternatives exist. The 3rd tier hands back the
    unfiltered pool (last resort) rather than [outgoing], since a real
    (if imperfect) alternative beats a no-op swap."""
    outgoing = _exercise("Push-up", difficulty_level=2)
    lower = _exercise("Knee push-up", difficulty_level=1)

    result = ScheduleService._tier_by_escalated_difficulty([outgoing, lower], outgoing)

    assert result == [outgoing, lower]
