import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CoachMemoryFact(Base):
    """One "заметка тренера" (2026-10-04, premium): a short, lasting fact
    about the player distilled from coach chat messages that have left the
    replayed history window (see CoachMemoryService). The whole list is
    rewritten on every summarization; the player can delete single facts
    or all of them from Settings."""

    __tablename__ = "coach_memory_facts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )


class CoachMemoryState(Base):
    """How far a player's chat has been summarized into CoachMemoryFact:
    every message with created_at <= summarized_until has been read (or
    deliberately skipped by "Забыть всё")."""

    __tablename__ = "coach_memory_states"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    summarized_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
