import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.coachmark_repository import CoachmarkRepository


class CoachmarkService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._coachmarks = CoachmarkRepository(session)

    async def list_seen(self, user_id: uuid.UUID) -> list[str]:
        return await self._coachmarks.list_seen_hint_ids(user_id)

    async def mark_seen(self, user_id: uuid.UUID, hint_id: str) -> list[str]:
        await self._coachmarks.mark_seen(user_id, hint_id)
        await self._session.commit()
        return await self._coachmarks.list_seen_hint_ids(user_id)
