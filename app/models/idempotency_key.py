import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IdempotencyKey(Base):
    """One workout write the client sent with an Idempotency-Key header
    (Б2, 2026-10-13). The offline queue resends an action until it hears a
    2xx -- a resend after a lost response must not log the set twice or pay
    XP twice. The row is inserted in the SAME transaction as the action
    itself (see app/core/idempotency.py), so "key stored" means "action
    applied"; the response is filled in right after and replayed as is to
    any repeat with the same key. Purged after 7 days (event_retention.py).
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_idempotency_keys_user_key"),
        Index("ix_idempotency_keys_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    # "POST /session-blocks/{id}/complete" with the real id -- the same key on
    # another request is the client's bug, refused rather than replayed.
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_json: Mapped[Any] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
