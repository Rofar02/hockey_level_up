import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import MovementPattern, MuscleGroup
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.repositories.user_temporary_restriction_repository import UserTemporaryRestrictionRepository

# How long a report lasts before it stops excluding exercises on its own --
# "auto-expires by date, can be lifted early" per the roadmap. No custom
# duration picker in this first pass, just one flat default.
DEFAULT_RESTRICTION_DAYS = 14


class UserTemporaryRestrictionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._restrictions = UserTemporaryRestrictionRepository(session)

    async def list_active(self, user: User) -> list[UserTemporaryRestriction]:
        return await self._restrictions.list_active_for_user(user.id, date.today())

    async def report(
        self,
        user: User,
        movement_pattern: MovementPattern | None,
        muscle_group: MuscleGroup | None,
        reason: str | None,
    ) -> UserTemporaryRestriction:
        """Reporting a target that's already actively restricted extends
        the existing row's expires_at rather than creating a second active
        row for it -- same upsert shape as TrainingDiaryService.save_entry.
        Exactly one of movement_pattern/muscle_group -- re-validated here
        (not just at the UserTemporaryRestrictionIn schema boundary) since
        this is also called directly, schema-free, and is what decides
        which of the two upsert lookups to use."""
        if (movement_pattern is None) == (muscle_group is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Specify exactly one of movement_pattern or muscle_group",
            )

        today = date.today()
        new_expires_at = today + timedelta(days=DEFAULT_RESTRICTION_DAYS)

        existing = (
            await self._restrictions.get_active_for_pattern(user.id, movement_pattern, today)
            if movement_pattern is not None
            else await self._restrictions.get_active_for_muscle_group(user.id, muscle_group, today)
        )
        if existing is not None:
            existing.expires_at = new_expires_at
            existing.reason = reason
            restriction = existing
        else:
            restriction = UserTemporaryRestriction(
                user_id=user.id,
                movement_pattern=movement_pattern,
                muscle_group=muscle_group,
                reason=reason,
                expires_at=new_expires_at,
            )
            await self._restrictions.save(restriction)

        await self._session.commit()
        return restriction

    async def lift(self, user: User, restriction_id: uuid.UUID) -> None:
        restriction = await self._restrictions.get_owned(user.id, restriction_id)
        if restriction is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restriction not found")
        # Idempotent -- lifting an already-lifted row is a harmless no-op,
        # not an error (re-clicking "снять" twice shouldn't fail).
        restriction.lifted_at = datetime.now(timezone.utc)
        await self._session.commit()
