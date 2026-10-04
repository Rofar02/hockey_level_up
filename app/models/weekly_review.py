import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WeeklyReview(Base):
    """The coach's Monday review of the previous week (2026-10-04, premium,
    see WeeklyReviewService). The numbers come from the analytics overview,
    only `text` is written by the model. The same text is also posted to
    the coach chat (`message_id`) so the player can reply to it."""

    __tablename__ = "weekly_reviews"
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_weekly_reviews_user_week"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Monday of the reviewed week.
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    sessions_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    sessions_planned: Mapped[int] = mapped_column(Integer, nullable=False)
    records_count: Mapped[int] = mapped_column(Integer, nullable=False)
    top_stat: Mapped[str | None] = mapped_column(String(32), nullable=True)
    top_stat_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coach_chat_messages.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    # Set when the player closes the card on Home.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
