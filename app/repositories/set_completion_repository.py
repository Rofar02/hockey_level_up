import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
