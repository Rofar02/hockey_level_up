from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent

BATCH_SIZE = 50


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, event_type: str, payload: dict) -> OutboxEvent:
        event = OutboxEvent(event_type=event_type, payload=payload)
        self._session.add(event)
        return event

    async def lock_unpublished_batch(self) -> list[OutboxEvent]:
        # FOR UPDATE SKIP LOCKED: rows already claimed by a concurrent relay
        # run are skipped instead of blocking, so two relay instances (or two
        # overlapping ticks of the same one) never publish the same row twice.
        result = await self._session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())
