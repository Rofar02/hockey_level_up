import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserCoachmark(Base):
    """One row per (user, hint_id) -- marks that this user has already been
    shown that particular first-touch tour step, so it never shows again,
    on any device (per-user, not per-browser -- see the frontend's own
    Coachmark overlay for why that matters: this replaces an earlier
    localStorage-only version that couldn't follow a user across devices).
    """

    __tablename__ = "user_coachmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "hint_id", name="uq_user_coachmarks_user_hint"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Free-form string id the frontend picks (e.g. "home-skill-milestones"),
    # not an enum -- new tour steps are added purely on the frontend, no
    # backend change needed per new hint.
    hint_id: Mapped[str] = mapped_column(String(100), nullable=False)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
