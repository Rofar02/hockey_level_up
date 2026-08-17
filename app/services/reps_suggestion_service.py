import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import Exercise, ExerciseType
from app.models.set_completion import SetFeedback
from app.models.user import User
from app.repositories.set_completion_repository import SetCompletionRepository
from app.repositories.training_block_repository import TrainingBlockRepository

# Double progression (Phase: П.1): how many more reps to suggest than last
# time, when the user didn't hit the top of the range with easy/normal
# feedback (that case resets to rep_range_min instead -- see
# suggest_reps). Fills in the handoff spec's "1-2 more reps" as a concrete,
# feedback-scaled rule: felt fine but hadn't hit the top yet -> push by 2;
# felt hard -> push by 1; felt maximal -> don't push further at all; no
# feedback recorded yet -> conservative +1.
_REPS_BUMP_BY_FEEDBACK: dict[SetFeedback | None, int] = {
    SetFeedback.EASY: 2,
    SetFeedback.NORMAL: 2,
    SetFeedback.HARD: 1,
    SetFeedback.MAX: 0,
    None: 1,
}


def _has_rep_range(exercise: Exercise) -> bool:
    return (
        exercise.exercise_type == ExerciseType.SETS_REPS
        and exercise.rep_range_min is not None
        and exercise.rep_range_max is not None
    )


class RepsSuggestionService:
    def __init__(self, session: AsyncSession) -> None:
        self._sets = SetCompletionRepository(session)
        self._blocks = TrainingBlockRepository(session)

    async def suggest_reps(self, user: User, exercise: Exercise) -> int | None:
        if not _has_rep_range(exercise):
            return None

        if await self._is_macrocycle_deload(user.id):
            # Floor regardless of history -- same whether this is the
            # user's first-ever set or their hundredth, so this skips the
            # SetCompletion lookups entirely (Phase: П.2).
            return exercise.rep_range_min

        last_set = await self._sets.get_last_for_user_exercise(user.id, exercise.id)
        if last_set is None:
            return exercise.rep_range_min

        if last_set.reps_completed is None:
            return exercise.rep_range_min

        last_session_sets = await self._sets.list_for_session_exercise(
            last_set.training_session_id, exercise.id
        )
        hit_top = bool(last_session_sets) and all(
            s.reps_completed is not None and s.reps_completed >= exercise.rep_range_max
            for s in last_session_sets
        )
        good_feedback = last_set.feedback in (SetFeedback.EASY, SetFeedback.NORMAL)

        if hit_top and good_feedback:
            return exercise.rep_range_min

        bump = _REPS_BUMP_BY_FEEDBACK[last_set.feedback]
        suggested = last_set.reps_completed + bump
        return max(exercise.rep_range_min, min(suggested, exercise.rep_range_max))

    async def _is_macrocycle_deload(self, user_id: uuid.UUID) -> bool:
        """Phase: П.2. Pure read, see WeightSuggestionService._is_macrocycle_deload."""
        block = await self._blocks.get_active_for_user(user_id)
        return block is not None and block.is_macrocycle_deload
