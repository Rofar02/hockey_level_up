import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coachmark import UserCoachmark


class CoachmarkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_seen_hint_ids(self, user_id: uuid.UUID) -> list[str]:
        result = await self._session.execute(
            select(UserCoachmark.hint_id).where(UserCoachmark.user_id == user_id)
        )
        return list(result.scalars().all())

    async def mark_seen(self, user_id: uuid.UUID, hint_id: str) -> None:
        """Idempotent -- re-marking an already-seen hint (a double-tap, two
        tabs open) is a no-op rather than an error, same convention as
        PushSubscriptionRepository.upsert."""
        stmt = (
            pg_insert(UserCoachmark)
            .values(user_id=user_id, hint_id=hint_id)
            .on_conflict_do_nothing(constraint="uq_user_coachmarks_user_hint")
        )
        await self._session.execute(stmt)
        await self._session.flush()
