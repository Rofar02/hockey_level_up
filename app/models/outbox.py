import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        # Matches what's actually in the DB (see `\d outbox_events` / pg_indexes):
        # CREATE INDEX ix_outbox_events_unpublished ON outbox_events USING
        # btree (created_at) WHERE (published_at IS NULL). Speeds up the
        # outbox relay's SELECT ... WHERE published_at IS NULL ORDER BY
        # created_at (see OutboxRepository.lock_unpublished_batch) -- was
        # created directly against the DB at some point without ever being
        # declared here, which is why alembic autogenerate kept proposing to
        # drop it on every unrelated migration.
        Index(
            "ix_outbox_events_unpublished",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
