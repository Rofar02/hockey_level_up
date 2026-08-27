import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import MovementPattern, MuscleGroup
from app.models.user_temporary_restriction import UserTemporaryRestriction


class UserTemporaryRestrictionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active_for_user(
        self, user_id: uuid.UUID, today: date
    ) -> list[UserTemporaryRestriction]:
        result = await self._session.execute(
            select(UserTemporaryRestriction)
            .where(
                UserTemporaryRestriction.user_id == user_id,
                UserTemporaryRestriction.expires_at >= today,
                UserTemporaryRestriction.lifted_at.is_(None),
            )
            .order_by(UserTemporaryRestriction.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_active_for_pattern(
        self, user_id: uuid.UUID, pattern: MovementPattern, today: date
    ) -> UserTemporaryRestriction | None:
        result = await self._session.execute(
            select(UserTemporaryRestriction).where(
                UserTemporaryRestriction.user_id == user_id,
                UserTemporaryRestriction.movement_pattern == pattern,
                UserTemporaryRestriction.expires_at >= today,
                UserTemporaryRestriction.lifted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    # Mirrors get_active_for_pattern exactly, muscle_group instead of
    # movement_pattern -- same upsert-on-repeat-report lookup, just for the
    # other of the two mutually-exclusive restriction targets.
    async def get_active_for_muscle_group(
        self, user_id: uuid.UUID, group: MuscleGroup, today: date
    ) -> UserTemporaryRestriction | None:
        result = await self._session.execute(
            select(UserTemporaryRestriction).where(
                UserTemporaryRestriction.user_id == user_id,
                UserTemporaryRestriction.muscle_group == group,
                UserTemporaryRestriction.expires_at >= today,
                UserTemporaryRestriction.lifted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_owned(
        self, user_id: uuid.UUID, restriction_id: uuid.UUID
    ) -> UserTemporaryRestriction | None:
        result = await self._session.execute(
            select(UserTemporaryRestriction).where(
                UserTemporaryRestriction.id == restriction_id,
                UserTemporaryRestriction.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def save(self, restriction: UserTemporaryRestriction) -> UserTemporaryRestriction:
        self._session.add(restriction)
        await self._session.flush()
        return restriction
