import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.processed_event import ProcessedEvent


async def try_claim(session: AsyncSession, event_id: uuid.UUID, handler_name: str) -> bool:
    """Atomically claim (event_id, handler_name) for processing.

    Callers must run this against the same session/transaction they'll use
    for their side-effect and commit both together -- that's what makes the
    claim and the side-effect land atomically (see ProcessedEvent).

    Returns True if this call claimed it (caller should proceed and commit).
    Returns False if it was already claimed (caller should skip -- some
    prior delivery, of possibly-duplicate at-least-once redelivery, already
    applied this handler's side-effect for this event).
    """
    result = await session.execute(
        pg_insert(ProcessedEvent)
        .values(event_id=event_id, handler_name=handler_name)
        .on_conflict_do_nothing(index_elements=[ProcessedEvent.event_id, ProcessedEvent.handler_name])
        .returning(ProcessedEvent.event_id)
    )
    return result.first() is not None
