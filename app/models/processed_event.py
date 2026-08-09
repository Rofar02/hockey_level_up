import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProcessedEvent(Base):
    """Per-handler idempotency marker for outbox-relayed events.

    (event_id, handler_name) is the composite primary key -- not event_id
    alone -- so each subscriber of an event claims its own row and is never
    blocked by (or blocks) another subscriber's claim. A handler inserts its
    row in the SAME transaction as the side-effect it guards (see
    app/events/idempotency.py): either both commit together, or -- if the
    side-effect fails -- the whole transaction rolls back and the claim
    disappears with it, so a retry can still claim and apply it.
    """

    __tablename__ = "processed_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    handler_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
