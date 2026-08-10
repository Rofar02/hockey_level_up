import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coach_chat import CoachChatMessage, CoachChatRole


class CoachChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_user_messages_since(self, user_id: uuid.UUID, since: datetime) -> int:
        """Used for the monthly message quota -- caller passes the start of
        the current calendar month as `since`."""
        result = await self._session.execute(
            select(func.count())
            .select_from(CoachChatMessage)
            .where(
                CoachChatMessage.user_id == user_id,
                CoachChatMessage.role == CoachChatRole.USER,
                CoachChatMessage.created_at >= since,
            )
        )
        return result.scalar_one()

    async def list_recent(self, user_id: uuid.UUID, limit: int) -> list[CoachChatMessage]:
        """Last `limit` messages, oldest first -- ready to replay straight
        into the Anthropic `messages` array as dialogue context."""
        result = await self._session.execute(
            select(CoachChatMessage)
            .where(CoachChatMessage.user_id == user_id)
            .order_by(CoachChatMessage.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    def add(
        self,
        user_id: uuid.UUID,
        role: CoachChatRole,
        content: str,
        created_at: datetime | None = None,
    ) -> CoachChatMessage:
        # created_at is caller-supplied when ordering across multiple rows
        # in the same call matters (see CoachChatService.send_message,
        # which adds a user + assistant row in one transaction) -- the
        # column's own default resolves via the wall clock, and two calls
        # microseconds apart can tie on a coarse-resolution clock.
        kwargs = {} if created_at is None else {"created_at": created_at}
        message = CoachChatMessage(user_id=user_id, role=role, content=content, **kwargs)
        self._session.add(message)
        return message
