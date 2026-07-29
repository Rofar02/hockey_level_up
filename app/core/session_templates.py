"""Skeleton config: share of session time per phase, by category.

Not used to derive exercise counts (Phase 2 hardcodes those directly per the
simple-rules spec) -- exposed alongside the assembled session so a client can
render phase proportions. Actual duration allocation is a later-phase concern.
"""
from app.models.exercise import ExerciseCategory, TrainingPhase

SESSION_TEMPLATES: dict[ExerciseCategory, dict[TrainingPhase, float]] = {
    ExerciseCategory.ON_ICE: {
        TrainingPhase.WARMUP: 0.15,
        TrainingPhase.MAIN: 0.75,
        TrainingPhase.COOLDOWN: 0.10,
    },
    ExerciseCategory.OFF_ICE: {
        TrainingPhase.WARMUP: 0.15,
        TrainingPhase.MAIN: 0.75,
        TrainingPhase.COOLDOWN: 0.10,
    },
}


def get_phase_split(category: ExerciseCategory) -> dict[TrainingPhase, float]:
    return SESSION_TEMPLATES[category]
