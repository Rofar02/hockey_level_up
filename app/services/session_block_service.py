import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import SessionBlock
from app.models.user import User
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.schedule_repository import ScheduleRepository

BLOCK_COMPLETED_EVENT = "block_completed"


class SessionBlockService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._schedule = ScheduleRepository(session)
        self._outbox = OutboxRepository(session)

    async def complete_block(self, block_id: uuid.UUID, user: User) -> SessionBlock:
        block = await self._schedule.get_session_block_with_owner(block_id)
        if block is None or block.session.day_plan.weekly_plan.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session block not found"
            )

        if block.completed_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="already completed"
            )

        block.completed_at = datetime.now(timezone.utc)
        # Outbox pattern: the event row is written in the same transaction as
        # completed_at, instead of publishing to RabbitMQ directly here. That
        # way a broker outage can't leave the block "burned" (completed with
        # no event ever sent) -- either both commit or neither does. A
        # separate relay task (app/events/outbox_relay.py) delivers the row
        # to RabbitMQ afterwards, independent of this request.
        self._outbox.add(
            BLOCK_COMPLETED_EVENT,
            {
                "user_id": str(user.id),
                "session_block_id": str(block.id),
                "exercise_id": str(block.exercise_id),
                "target_stat": block.exercise.target_stat.value,
                "difficulty_level": block.exercise.difficulty_level,
            },
        )
        await self._session.commit()
        return block
