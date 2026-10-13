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
- refresh_sessions (2026-10-13, А11): a device session past its expires_at
  can never refresh again; login only tidies up the player's own.
- idempotency_keys (Б2): a resend from the offline queue comes within hours
  (48 h at most, see training_day.PERFORMED_AT_MAX_AGE); kept a week.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.core.idempotency import RETENTION_DAYS as IDEMPOTENCY_RETENTION_DAYS
from app.models.idempotency_key import IdempotencyKey
from app.models.outbox import OutboxEvent
from app.models.processed_event import ProcessedEvent
from app.models.refresh_session import RefreshSession
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


async def purge_expired_sessions(session: AsyncSession, now_utc: datetime) -> int:
    result = await session.execute(delete(RefreshSession).where(RefreshSession.expires_at <= now_utc))
    return result.rowcount


async def purge_old_idempotency_keys(session: AsyncSession, now_utc: datetime) -> int:
    cutoff = now_utc - timedelta(days=IDEMPOTENCY_RETENTION_DAYS)
    result = await session.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < cutoff))
    return result.rowcount


async def _retention_tick() -> None:
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session, session.begin():
        outbox_deleted, processed_deleted = await purge_old_events(session, now_utc)
        sessions_deleted = await purge_expired_sessions(session, now_utc)
        keys_deleted = await purge_old_idempotency_keys(session, now_utc)
    logger.info(
        "Event retention: deleted %s outbox_events, %s processed_events older than %s days, "
        "%s expired refresh sessions, %s idempotency keys",
        outbox_deleted,
        processed_deleted,
        RETENTION_DAYS,
        sessions_deleted,
        keys_deleted,
    )


async def run_event_retention() -> None:
    while True:
        try:
            await _retention_tick()
        except Exception:
            logger.exception("Event retention tick failed")
        await asyncio.sleep(TICK_INTERVAL_SECONDS)
