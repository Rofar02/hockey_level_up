import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import EquipmentType, Exercise, ExerciseType
from app.models.set_completion import SetCompletion, SetFeedback
from app.models.user import FitnessTier, User
from app.repositories.set_completion_repository import SetCompletionRepository
from app.repositories.training_block_repository import TrainingBlockRepository

_TIER_MULTIPLIER: dict[FitnessTier, float] = {
    FitnessTier.BEGINNER: 0.7,
    FitnessTier.INTERMEDIATE: 1.0,
    FitnessTier.ADVANCED: 1.3,
}

_FEEDBACK_ADJUSTMENT: dict[SetFeedback, float] = {
    SetFeedback.EASY: 1.05,
    SetFeedback.NORMAL: 1.025,
    SetFeedback.HARD: 1.0,
    SetFeedback.MAX: 0.95,
}

# EquipmentType only distinguishes gym / home / bodyweight -- it doesn't
# separate "barbell or plate-loaded machine" from "dumbbell" the way the
# rounding rule wants. Closest available mapping, flagged rather than
# invented silently: gym work (barbells, machines) rounds to 2.5kg plates;
# home equipment (adjustable dumbbells) rounds to 1kg. A real barbell-vs-
# dumbbell distinction would need a new field on Exercise if this mapping
# turns out wrong for some exercise.
_ROUNDING_STEP_KG: dict[EquipmentType, float] = {
    EquipmentType.GYM: 2.5,
    EquipmentType.HOME: 1.0,
    EquipmentType.BODYWEIGHT: 1.0,
}

# Double progression (Phase: П.1): weeks since the exercise's last logged set
# before its suggested weight gets discounted, on top of whatever the
# feedback-based adjustment already computed -- a long layoff means the
# feedback from that last set is stale evidence of current capability.
_DETRAINING_COEFFICIENT_BY_WEEKS: list[tuple[int, float]] = [
    (8, 0.8),
    (4, 0.9),
]

# Macrocycle deload (Phase: П.2): deeper than the steepest detraining
# discount above (0.8) -- a scheduled recovery block should be unmistakably
# lighter than "just been away 8 weeks", not the same number by coincidence.
MACROCYCLE_DELOAD_WEIGHT_MULTIPLIER = 0.7


def _round_to_step(value: float, step: float) -> float:
    return round(value / step) * step


def _detraining_coefficient(last_completed_at: datetime) -> float:
    gap_weeks = (datetime.now(timezone.utc) - last_completed_at).days // 7
    for threshold_weeks, coefficient in _DETRAINING_COEFFICIENT_BY_WEEKS:
        if gap_weeks >= threshold_weeks:
            return coefficient
    return 1.0


def _has_rep_range(exercise: Exercise) -> bool:
    return (
        exercise.exercise_type == ExerciseType.SETS_REPS
        and exercise.rep_range_min is not None
        and exercise.rep_range_max is not None
    )


class WeightSuggestionService:
    def __init__(self, session: AsyncSession) -> None:
        self._sets = SetCompletionRepository(session)
        self._blocks = TrainingBlockRepository(session)

    async def suggest_weight(self, user: User, exercise: Exercise) -> float | None:
        if not exercise.tracks_weight:
            return None

        step = _ROUNDING_STEP_KG[exercise.equipment_type]
        last_set = await self._sets.get_last_for_user_exercise(user.id, exercise.id)

        if last_set is not None:
            if last_set.weight_kg is None:
                return None
            if await self._is_macrocycle_deload(user.id):
                # Floor only -- not further modulated by this session's
                # feedback or a separate staleness discount, see
                # MACROCYCLE_DELOAD_WEIGHT_MULTIPLIER.
                return _round_to_step(
                    last_set.weight_kg * MACROCYCLE_DELOAD_WEIGHT_MULTIPLIER, step
                )
            adjustment = await self._feedback_adjustment(last_set, exercise)
            detraining = _detraining_coefficient(last_set.completed_at)
            return _round_to_step(last_set.weight_kg * adjustment * detraining, step)

        if user.weight is None or exercise.bodyweight_ratio is None:
            return None

        # Fitness test not taken yet -- default to intermediate rather than
        # guessing beginner/advanced with no signal either way.
        tier = user.fitness_tier if user.fitness_tier is not None else FitnessTier.INTERMEDIATE
        raw = user.weight * exercise.bodyweight_ratio * _TIER_MULTIPLIER[tier]
        return _round_to_step(raw, step)

    async def _feedback_adjustment(self, last_set: SetCompletion, exercise: Exercise) -> float:
        """Double progression (Phase: П.1): for a rep-range exercise, weight
        only grows once the user hit the top of the range on every set of
        their last session for it *and* that felt easy/normal -- not on any
        easy/normal feedback regardless of reps, which is what the plain
        feedback table below still does for every other exercise (no rep
        range configured yet, e.g. not-yet-backfilled or duration-type).
        RepsSuggestionService is what actually pushes reps up in the
        "same weight, more reps" branch -- this service only ever reacts by
        holding weight steady or (on MAX) backing off.
        """
        if last_set.feedback is None:
            return 1.0
        if not _has_rep_range(exercise):
            return _FEEDBACK_ADJUSTMENT[last_set.feedback]

        last_session_sets = await self._sets.list_for_session_exercise(
            last_set.training_session_id, exercise.id
        )
        hit_top = bool(last_session_sets) and all(
            s.reps_completed is not None and s.reps_completed >= exercise.rep_range_max
            for s in last_session_sets
        )
        good_feedback = last_set.feedback in (SetFeedback.EASY, SetFeedback.NORMAL)

        if hit_top and good_feedback:
            return _FEEDBACK_ADJUSTMENT[last_set.feedback]
        if last_set.feedback == SetFeedback.MAX:
            return _FEEDBACK_ADJUSTMENT[SetFeedback.MAX]
        return 1.0

    async def _is_macrocycle_deload(self, user_id: uuid.UUID) -> bool:
        """Phase: П.2. A pure read (TrainingBlockRepository.get_active_for_user
        never mutates/advances, unlike TrainingBlockService.resolve_active_block)
        -- safe to call from this read-only suggestion path."""
        block = await self._blocks.get_active_for_user(user_id)
        return block is not None and block.is_macrocycle_deload
