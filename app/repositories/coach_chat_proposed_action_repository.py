import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coach_chat_proposed_action import CoachActionStatus, CoachChatProposedAction


class CoachChatProposedActionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def create(self, action: CoachChatProposedAction) -> CoachChatProposedAction:
        self._session.add(action)
        return action

    async def get_owned(
        self, user_id: uuid.UUID, action_id: uuid.UUID
    ) -> CoachChatProposedAction | None:
        result = await self._session.execute(
            select(CoachChatProposedAction).where(
                CoachChatProposedAction.id == action_id,
                CoachChatProposedAction.user_id == user_id,
            )
        )
        return result.scalars().first()

    async def expire_pending_for_user(self, user_id: uuid.UUID) -> None:
        """Marks any still-PENDING action for this user as EXPIRED -- called
        right before creating a new one, since only one proposal should
        ever be confirmable at a time (see CoachChatProposedAction's own
        docstring for why: a stale proposal from earlier in the
        conversation shouldn't get confirmed against a since-moved-on
        context)."""
        await self._session.execute(
            update(CoachChatProposedAction)
            .where(
                CoachChatProposedAction.user_id == user_id,
                CoachChatProposedAction.status == CoachActionStatus.PENDING,
            )
            .values(status=CoachActionStatus.EXPIRED)
        )

    async def list_by_message_ids(
        self, message_ids: list[uuid.UUID]
    ) -> list[CoachChatProposedAction]:
        if not message_ids:
            return []
        result = await self._session.execute(
            select(CoachChatProposedAction).where(
                CoachChatProposedAction.message_id.in_(message_ids)
            )
        )
        return list(result.scalars().all())
