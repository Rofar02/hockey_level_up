"""Daily cleanup of the two event bookkeeping tables, which otherwise grow
forever -- ~40% of all database growth in a year-long simulation
(2026-09-28), and the biggest tables on prod.

- outbox_events: once published, a row only matters to the friend activity
  feed, and only for FEED_EVENT_TYPES (it reads those straight from this
  table, with no time window). Everything else -- mostly block_completed,
  ~90% of the rows -- is dropped RETENTION_DAYS after publishing. Unpublished
  rows are never touched; the relay still owes them a delivery.
- processed_events: the consumer's "already handled" marks. They guard
  against a redelivered message, which happens within minutes of the
  original, not weeks later.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.outbox import OutboxEvent
from app.models.processed_event import ProcessedEvent
from app.services.friend_activity_service import FEED_EVENT_TYPES

logger = logging.getLogger(__name__)

RETENTION_DAYS = 30
TICK_INTERVAL_SECONDS = 24 * 60 * 60


async def purge_old_events(session: AsyncSession, now_utc: datetime) -> tuple[int, int]:
    """Returns (outbox rows deleted, processed_events rows deleted)."""
    cutoff = now_utc - timedelta(days=RETENTION_DAYS)
    outbox = await session.execute(
        delete(OutboxEvent).where(
            OutboxEvent.published_at.is_not(None),
            OutboxEvent.published_at < cutoff,
            OutboxEvent.event_type.notin_(FEED_EVENT_TYPES),
        )
    )
    processed = await session.execute(delete(ProcessedEvent).where(ProcessedEvent.processed_at < cutoff))
    return outbox.rowcount, processed.rowcount


async def _retention_tick() -> None:
    async with AsyncSessionLocal() as session, session.begin():
        outbox_deleted, processed_deleted = await purge_old_events(session, datetime.now(timezone.utc))
    logger.info(
        "Event retention: deleted %s outbox_events, %s processed_events older than %s days",
        outbox_deleted,
        processed_deleted,
        RETENTION_DAYS,
    )


async def run_event_retention() -> None:
    while True:
        try:
            await _retention_tick()
        except Exception:
            logger.exception("Event retention tick failed")
        await asyncio.sleep(TICK_INTERVAL_SECONDS)
