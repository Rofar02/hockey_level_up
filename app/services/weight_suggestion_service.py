from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import EquipmentType, Exercise
from app.models.set_completion import SetFeedback
from app.models.user import FitnessTier, User
from app.repositories.set_completion_repository import SetCompletionRepository

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


def _round_to_step(value: float, step: float) -> float:
    return round(value / step) * step


class WeightSuggestionService:
    def __init__(self, session: AsyncSession) -> None:
        self._sets = SetCompletionRepository(session)

    async def suggest_weight(self, user: User, exercise: Exercise) -> float | None:
        if not exercise.tracks_weight:
            return None

        step = _ROUNDING_STEP_KG[exercise.equipment_type]
        last_set = await self._sets.get_last_for_user_exercise(user.id, exercise.id)

        if last_set is not None:
            if last_set.weight_kg is None:
                return None
            adjustment = (
                1.0 if last_set.feedback is None else _FEEDBACK_ADJUSTMENT[last_set.feedback]
            )
            return _round_to_step(last_set.weight_kg * adjustment, step)

        if user.weight is None or exercise.bodyweight_ratio is None:
            return None

        # Fitness test not taken yet -- default to intermediate rather than
        # guessing beginner/advanced with no signal either way.
        tier = user.fitness_tier if user.fitness_tier is not None else FitnessTier.INTERMEDIATE
        raw = user.weight * exercise.bodyweight_ratio * _TIER_MULTIPLIER[tier]
        return _round_to_step(raw, step)
