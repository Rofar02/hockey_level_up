import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import (
    ExerciseCategory,
    MovementPattern,
    StimulusType,
    UserMovementPatternVariant,
)


class UserMovementPatternVariantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user_category(
        self, user_id: uuid.UUID, category: ExerciseCategory
    ) -> dict[tuple[MovementPattern, StimulusType | None], UserMovementPatternVariant]:
        """Bulk fetch, live ORM rows (not detached values) -- callers mutate
        these in place and rely on the caller's existing flush/commit
        boundary, same as TrainingBlockRepository.get_active_for_user's row
        being mutated directly by TrainingBlockService._advance.

        Keyed by (movement_pattern, archetype) since Stage 2.4 -- a pattern
        outside app.core.day_archetype.ARCHETYPE_ELIGIBLE_PATTERNS has
        exactly one row here, keyed with archetype=None, identical to the
        pre-2.4 shape; an eligible pattern can have up to three, one per
        StimulusType.STRENGTH/POWER/SKILL.
        """
        result = await self._session.execute(
            select(UserMovementPatternVariant).where(
                UserMovementPatternVariant.user_id == user_id,
                UserMovementPatternVariant.category == category,
            )
        )
        return {(row.movement_pattern, row.archetype): row for row in result.scalars().all()}
