"""purge_old_events keeps what anything still reads: unpublished outbox rows
(the relay owes them a delivery), feed event types (the friend feed reads
them with no time window) and anything recent."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.outbox import OutboxEvent
from app.models.processed_event import ProcessedEvent
from app.services.event_retention import RETENTION_DAYS, purge_old_events

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
OLD = NOW - timedelta(days=RETENTION_DAYS + 1)
RECENT = NOW - timedelta(days=RETENTION_DAYS - 1)


def _event(event_type: str, created_at: datetime, published_at: datetime | None) -> OutboxEvent:
    return OutboxEvent(
        id=uuid.uuid4(),
        event_type=event_type,
        payload={"user_id": str(uuid.uuid4()), "marker": "retention-test"},
        created_at=created_at,
        published_at=published_at,
    )


@pytest.mark.asyncio
async def test_purge_drops_only_old_published_non_feed_events(db_session) -> None:
    old_block = _event("block_completed", OLD, OLD)
    recent_block = _event("block_completed", RECENT, RECENT)
    old_unpublished = _event("block_completed", OLD, None)
    old_feed_training = _event("training_completed", OLD, OLD)
    old_feed_level = _event("level_up", OLD, OLD)
    db_session.add_all([old_block, recent_block, old_unpublished, old_feed_training, old_feed_level])
    await db_session.flush()

    await purge_old_events(db_session, NOW)

    remaining = set(
        (
            await db_session.execute(
                select(OutboxEvent.id).where(OutboxEvent.payload["marker"].astext == "retention-test")
            )
        ).scalars()
    )
    assert remaining == {recent_block.id, old_unpublished.id, old_feed_training.id, old_feed_level.id}


@pytest.mark.asyncio
async def test_purge_drops_old_processed_marks_only(db_session) -> None:
    old_mark = ProcessedEvent(event_id=uuid.uuid4(), handler_name="retention_test", processed_at=OLD)
    recent_mark = ProcessedEvent(event_id=uuid.uuid4(), handler_name="retention_test", processed_at=RECENT)
    db_session.add_all([old_mark, recent_mark])
    await db_session.flush()

    await purge_old_events(db_session, NOW)

    remaining = set(
        (
            await db_session.execute(
                select(ProcessedEvent.event_id).where(ProcessedEvent.handler_name == "retention_test")
            )
        ).scalars()
    )
    assert remaining == {recent_mark.event_id}
