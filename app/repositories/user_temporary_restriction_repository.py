import uuid
from datetime import date

from sqlalchemy import or_, select
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

    async def list_resolved_for_user(
        self, user_id: uuid.UUID, today: date, limit: int
    ) -> list[UserTemporaryRestriction]:
        """Restrictions that are no longer active (lifted early, or their
        expires_at has passed) -- distinct from list_active_for_user above.
        Used by CoachChatService's season-memory summary: "what's come up
        over time," not just what's active right now, which
        list_active_for_user already covers separately."""
        result = await self._session.execute(
            select(UserTemporaryRestriction)
            .where(
                UserTemporaryRestriction.user_id == user_id,
                or_(
                    UserTemporaryRestriction.lifted_at.is_not(None),
                    UserTemporaryRestriction.expires_at < today,
                ),
            )
            .order_by(UserTemporaryRestriction.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_for_prompt(
        self, user_id: uuid.UUID
    ) -> list[UserTemporaryRestriction]:
        """Every restriction (active and resolved alike), newest first, in
        one query -- UserTemporaryRestrictionService.list_for_coach_prompt
        splits this into active vs. resolved(capped) in Python instead of
        two separate queries with complementary WHERE clauses (this
        method's own list_active_for_user/list_resolved_for_user above),
        which is what the AI coach's system prompt used to call."""
        result = await self._session.execute(
            select(UserTemporaryRestriction)
            .where(UserTemporaryRestriction.user_id == user_id)
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
