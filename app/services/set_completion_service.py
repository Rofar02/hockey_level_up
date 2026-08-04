import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import Exercise
from app.models.set_completion import SetCompletion, SetFeedback
from app.models.user import User
from app.repositories.exercise_repository import ExerciseRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.repositories.set_completion_repository import SetCompletionRepository
from app.services.weight_suggestion_service import WeightSuggestionService

# Guard against a fat-fingered weight (e.g. 500 instead of 50kg) -- 3x the
# server-computed suggestion is generous headroom for a real jump in
# progression, so anything past it is treated as a typo and rejected with a
# 400 rather than silently clamped.
_WEIGHT_SANITY_MULTIPLIER = 3
_WEIGHT_EQUALITY_EPSILON = 0.01


class SetCompletionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sets = SetCompletionRepository(session)
        self._exercises = ExerciseRepository(session)
        self._schedule = ScheduleRepository(session)
        self._weight_suggestion = WeightSuggestionService(session)

    async def _get_owned_exercise_in_session(
        self, user: User, training_session_id: uuid.UUID, exercise_id: uuid.UUID
    ) -> Exercise:
        training_session = await self._schedule.get_training_session_with_owner(training_session_id)
        if training_session is None or training_session.day_plan.weekly_plan.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Training session not found"
            )
        if not any(block.exercise_id == exercise_id for block in training_session.blocks):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Exercise is not part of this training session",
            )

        exercise = await self._exercises.get_by_id(exercise_id)
        if exercise is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found")
        return exercise

    async def save_set(
        self,
        user: User,
        exercise_id: uuid.UUID,
        training_session_id: uuid.UUID,
        set_number: int,
        weight_kg: float | None,
        reps_completed: int | None,
        duration_seconds_completed: int | None,
    ) -> SetCompletion:
        exercise = await self._get_owned_exercise_in_session(user, training_session_id, exercise_id)

        if exercise.tracks_weight and (weight_kg is None or weight_kg <= 0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="weight_kg is required and must be greater than 0 for this exercise",
            )

        # Always recomputed server-side from history, never trusted from the
        # client -- this is also what the *3 sanity check below compares
        # against, so a client-supplied "suggested" value could otherwise be
        # used to bypass it.
        suggested_weight_kg = await self._weight_suggestion.suggest_weight(user, exercise)

        if (
            weight_kg is not None
            and suggested_weight_kg is not None
            and weight_kg >= suggested_weight_kg * _WEIGHT_SANITY_MULTIPLIER
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"weight_kg ({weight_kg}) looks like a typo: it's more than "
                    f"{_WEIGHT_SANITY_MULTIPLIER}x the suggested {suggested_weight_kg}kg"
                ),
            )

        was_adjusted = (
            weight_kg is not None
            and suggested_weight_kg is not None
            and abs(weight_kg - suggested_weight_kg) > _WEIGHT_EQUALITY_EPSILON
        )

        existing = await self._sets.get_by_session_exercise_set(
            training_session_id, exercise_id, set_number
        )
        if existing is not None:
            # Re-submitting the same set (e.g. correcting a typo before
            # moving to the next one) overwrites in place -- the unique
            # constraint exists to keep set_number honest, not to block
            # corrections.
            existing.weight_kg = weight_kg
            existing.reps_completed = reps_completed
            existing.duration_seconds_completed = duration_seconds_completed
            existing.suggested_weight_kg = suggested_weight_kg
            existing.was_weight_adjusted_manually = was_adjusted
            set_completion = existing
        else:
            set_completion = SetCompletion(
                user_id=user.id,
                exercise_id=exercise_id,
                training_session_id=training_session_id,
                set_number=set_number,
                weight_kg=weight_kg,
                reps_completed=reps_completed,
                duration_seconds_completed=duration_seconds_completed,
                suggested_weight_kg=suggested_weight_kg,
                was_weight_adjusted_manually=was_adjusted,
                completed_at=datetime.now(timezone.utc),
            )
            await self._sets.save(set_completion)

        await self._session.commit()
        return set_completion

    async def list_sets(
        self, user: User, exercise_id: uuid.UUID, training_session_id: uuid.UUID
    ) -> list[SetCompletion]:
        await self._get_owned_exercise_in_session(user, training_session_id, exercise_id)
        return await self._sets.list_for_session_exercise(training_session_id, exercise_id)

    async def save_feedback(
        self,
        user: User,
        exercise_id: uuid.UUID,
        training_session_id: uuid.UUID,
        feedback: SetFeedback,
    ) -> SetCompletion:
        await self._get_owned_exercise_in_session(user, training_session_id, exercise_id)

        last_set = await self._sets.get_last_in_session_for_exercise(
            training_session_id, exercise_id
        )
        if last_set is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No sets logged yet for this exercise in this session",
            )

        last_set.feedback = feedback
        await self._session.commit()
        return last_set
