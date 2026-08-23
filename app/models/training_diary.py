import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TrainingDiaryEntry(Base):
    """A player's own notebook entry for a single ON_ICE or GAME
    TrainingSession -- the app has no structured content for either (see
    ScheduleService._build_on_ice_day_session / _build_game_day_session),
    so free text is the only way the player can record what actually
    happened. Deliberately not fed into OverloadService's brakes (see
    app.core.overload) -- that mechanism counts individual sets within a
    session, a different granularity than one day-level judgment; wiring
    it in needs its own dedicated design, not a bolted-on hack here.

    Free text only -- no structured quick-tag (a first version had one,
    reusing SetFeedback, but the user wants the player to describe how it
    went in their own words rather than picking a canned label).

    One row per TrainingSession (unique constraint below), upserted in
    place on every save rather than accumulating a history -- see
    TrainingDiaryService.save_entry.
    """

    __tablename__ = "training_diary_entries"
    __table_args__ = (
        UniqueConstraint("training_session_id", name="uq_training_diary_entries_session"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Denormalized, same convention as SetCompletion.user_id -- avoids a
    # join through TrainingSession->DayPlan->WeeklyPlan for the common
    # "this user's diary entries" access pattern.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    training_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
