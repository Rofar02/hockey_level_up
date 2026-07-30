import asyncio
import logging
from datetime import datetime, timezone

from app.db.session import AsyncSessionLocal
from app.events.publisher import publish_event
from app.repositories.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.5


async def _relay_batch() -> int:
    async with AsyncSessionLocal() as session:
        outbox = OutboxRepository(session)
        # Everything below runs inside one transaction: the SELECT ... FOR
        # UPDATE SKIP LOCKED row locks are held until commit/rollback at the
        # end of this block, so a second relay tick (or a second relay
        # process) that runs concurrently skips these same rows instead of
        # racing to publish them twice.
        async with session.begin():
            events = await outbox.lock_unpublished_batch()

            for event in events:
                try:
                    await publish_event(event.event_type, event.payload)
                except Exception:
                    logger.exception(
                        "Outbox relay failed to publish outbox_event_id=%s event_type=%s; "
                        "will retry next cycle",
                        event.id,
                        event.event_type,
                    )
                    continue
                event.published_at = datetime.now(timezone.utc)

        return len(events)


async def run_outbox_relay() -> None:
    while True:
        try:
            await _relay_batch()
        except Exception:
            logger.exception("Outbox relay tick failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
