import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import MovementPattern, MuscleGroup
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.repositories.user_temporary_restriction_repository import UserTemporaryRestrictionRepository
from app.services.schedule_service import ScheduleService

# How long a report lasts before it stops excluding exercises on its own --
# "auto-expires by date, can be lifted early" per the roadmap. No custom
# duration picker in this first pass, just one flat default.
DEFAULT_RESTRICTION_DAYS = 14


class UserTemporaryRestrictionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._restrictions = UserTemporaryRestrictionRepository(session)
        self._schedule = ScheduleService(session)

    async def list_active(self, user: User) -> list[UserTemporaryRestriction]:
        # 2026-09-18 fix (audit round 2 item #3): date.today() read the
        # *server's* timezone -- see ProgressService.get_streak's matching
        # fix for the full reasoning.
        today = datetime.now(ZoneInfo(user.timezone)).date()
        return await self._restrictions.list_active_for_user(user.id, today)

    async def list_resolved(self, user: User, limit: int) -> list[UserTemporaryRestriction]:
        today = datetime.now(ZoneInfo(user.timezone)).date()
        return await self._restrictions.list_resolved_for_user(user.id, today, limit)

    async def list_for_coach_prompt(
        self, user: User, resolved_limit: int
    ) -> tuple[list[UserTemporaryRestriction], list[UserTemporaryRestriction]]:
        """(active, resolved) in one query instead of the two list_active/
        list_resolved calls above -- both read the same rows split by a
        complementary condition, so CoachChatService's system-prompt
        builder (the only caller that needs both at once) fetches the full
        list once and splits it here rather than round-tripping twice."""
        today = datetime.now(ZoneInfo(user.timezone)).date()
        all_restrictions = await self._restrictions.list_for_prompt(user.id)
        active = [
            r for r in all_restrictions if r.lifted_at is None and r.expires_at >= today
        ]
        resolved = [
            r for r in all_restrictions if r.lifted_at is not None or r.expires_at < today
        ][:resolved_limit]
        return active, resolved

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

        today = datetime.now(ZoneInfo(user.timezone)).date()
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

        # 2026-09-19 audit round 3 item #2: a newly-reported restriction
        # only excluded a movement/muscle from *future* day/week assembly
        # -- see ScheduleService.patch_week_for_eligibility_change's own
        # docstring for the full "why". Same transaction as the restriction
        # row itself (that method never commits on its own), so a patched
        # week can never land without the restriction that caused it, or
        # vice versa.
        await self._schedule.patch_week_for_eligibility_change(user)
        await self._session.commit()
        return restriction

    async def lift(self, user: User, restriction_id: uuid.UUID) -> None:
        restriction = await self._restrictions.get_owned(user.id, restriction_id)
        if restriction is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restriction not found")
        # Idempotent -- lifting an already-lifted row is a harmless no-op,
        # not an error (re-clicking "снять" twice shouldn't fail).
        restriction.lifted_at = datetime.now(timezone.utc)
        # Symmetric with report() above (see that call's own comment) --
        # a no-op in practice today (lifting only widens the pool, and
        # nothing already-scheduled ever needs undoing), kept for the same
        # "any pool-affecting change" contract rather than special-casing
        # lift as the one trigger that skips it.
        await self._schedule.patch_week_for_eligibility_change(user)
        await self._session.commit()
