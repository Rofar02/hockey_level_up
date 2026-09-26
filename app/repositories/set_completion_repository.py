import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import DayPlan, TrainingBlock, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion


class SetCompletionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_last_for_user_exercise(
        self, user_id: uuid.UUID, exercise_id: uuid.UUID
    ) -> SetCompletion | None:
        """Most recent set logged for this user+exercise, across any session."""
        result = await self._session.execute(
            select(SetCompletion)
            .where(SetCompletion.user_id == user_id, SetCompletion.exercise_id == exercise_id)
            .order_by(SetCompletion.completed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_last_for_user_exercise_outside_block(
        self, user_id: uuid.UUID, exercise_id: uuid.UUID, training_block_id: uuid.UUID
    ) -> SetCompletion | None:
        """Most recent set for this user+exercise logged in a week that
        doesn't belong to `training_block_id` -- i.e. before that block."""
        result = await self._session.execute(
            select(SetCompletion)
            .join(TrainingSession, TrainingSession.id == SetCompletion.training_session_id)
            .join(DayPlan, DayPlan.id == TrainingSession.day_plan_id)
            .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
            .where(
                SetCompletion.user_id == user_id,
                SetCompletion.exercise_id == exercise_id,
                or_(WeeklyPlan.training_block_id.is_(None), WeeklyPlan.training_block_id != training_block_id),
            )
            .order_by(SetCompletion.completed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_last_for_user_exercise_outside_macrocycle_deloads(
        self, user_id: uuid.UUID, exercise_id: uuid.UUID
    ) -> SetCompletion | None:
        """Most recent set for this user+exercise logged outside any
        macrocycle-deload block -- the real working weight a deload block
        steps back from."""
        result = await self._session.execute(
            select(SetCompletion)
            .join(TrainingSession, TrainingSession.id == SetCompletion.training_session_id)
            .join(DayPlan, DayPlan.id == TrainingSession.day_plan_id)
            .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
            .outerjoin(TrainingBlock, TrainingBlock.id == WeeklyPlan.training_block_id)
            .where(
                SetCompletion.user_id == user_id,
                SetCompletion.exercise_id == exercise_id,
                or_(TrainingBlock.id.is_(None), TrainingBlock.is_macrocycle_deload.is_(False)),
            )
            .order_by(SetCompletion.completed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_recent_for_user_exercise(
        self, user_id: uuid.UUID, exercise_id: uuid.UUID, limit: int
    ) -> list[SetCompletion]:
        """Most recent `limit` sets logged for this user+exercise, newest
        first, possibly spanning several sessions -- unlike
        get_last_for_user_exercise (a single row), this lets a caller
        compare across sessions (e.g. CoachChatService's exercise-dynamics
        section, which walks these to find the last set of each of the
        two most recent sessions)."""
        result = await self._session.execute(
            select(SetCompletion)
            .where(SetCompletion.user_id == user_id, SetCompletion.exercise_id == exercise_id)
            .order_by(SetCompletion.completed_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_session_exercise_set(
        self, training_session_id: uuid.UUID, exercise_id: uuid.UUID, set_number: int
    ) -> SetCompletion | None:
        result = await self._session.execute(
            select(SetCompletion).where(
                SetCompletion.training_session_id == training_session_id,
                SetCompletion.exercise_id == exercise_id,
                SetCompletion.set_number == set_number,
            )
        )
        return result.scalar_one_or_none()

    async def get_last_in_session_for_exercise(
        self, training_session_id: uuid.UUID, exercise_id: uuid.UUID
    ) -> SetCompletion | None:
        """Highest set_number logged so far for this exercise in this session --
        the row the feedback endpoint updates."""
        result = await self._session.execute(
            select(SetCompletion)
            .where(
                SetCompletion.training_session_id == training_session_id,
                SetCompletion.exercise_id == exercise_id,
            )
            .order_by(SetCompletion.set_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_session_exercise(
        self, training_session_id: uuid.UUID, exercise_id: uuid.UUID
    ) -> list[SetCompletion]:
        result = await self._session.execute(
            select(SetCompletion)
            .where(
                SetCompletion.training_session_id == training_session_id,
                SetCompletion.exercise_id == exercise_id,
            )
            .order_by(SetCompletion.set_number)
        )
        return list(result.scalars().all())

    async def save(self, set_completion: SetCompletion) -> SetCompletion:
        self._session.add(set_completion)
        await self._session.flush()
        return set_completion
