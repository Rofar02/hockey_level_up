import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import ExerciseCategory, MovementPattern, UserMovementPatternVariant


class UserMovementPatternVariantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user_category(
        self, user_id: uuid.UUID, category: ExerciseCategory
    ) -> dict[MovementPattern, UserMovementPatternVariant]:
        """Bulk fetch, live ORM rows (not detached values) -- callers mutate
        these in place and rely on the caller's existing flush/commit
        boundary, same as TrainingBlockRepository.get_active_for_user's row
        being mutated directly by TrainingBlockService._advance."""
        result = await self._session.execute(
            select(UserMovementPatternVariant).where(
                UserMovementPatternVariant.user_id == user_id,
                UserMovementPatternVariant.category == category,
            )
        )
        return {row.movement_pattern: row for row in result.scalars().all()}
