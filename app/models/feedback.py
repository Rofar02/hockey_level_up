import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column


class FeedbackKind(enum.StrEnum):
    BUG = "bug"
    IDEA = "idea"
    OTHER = "other"


class FeedbackStatus(enum.StrEnum):
    NEW = "new"
    SEEN = "seen"
    DONE = "done"


class Feedback(Base):
    """A message from a player to the developer (2026-10-04): a bug, an idea
    or anything else, with an optional screenshot and the device context
    the app attaches by itself (page, browser, screen, home-screen app)."""

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[FeedbackKind] = mapped_column(enum_column(FeedbackKind, "feedback_kind", length=16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # File name under settings.feedback_upload_dir (private, admin-only).
    screenshot_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[FeedbackStatus] = mapped_column(
        enum_column(FeedbackStatus, "feedback_status", length=16), nullable=False, default=FeedbackStatus.NEW
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
