import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column
from app.models.exercise import MovementPattern


class UserTemporaryRestriction(Base):
    """A player-reported "this movement hurts right now" flag -- excludes
    every exercise tagged with `movement_pattern` from assembly (MAIN,
    warmup, cooldown, GAME activation, party suggestions -- everywhere,
    see ExerciseRepository.list_for_assembly) for as long as it's active.

    Manual report only for now (P3 item #7, first pass) -- a player
    messages the coach and an AI classifies the free text into a pattern
    is a later layer on top of this same table, not built yet.

    Active = expires_at >= today AND lifted_at IS NULL. Expired/lifted
    rows are kept, not deleted -- a later feature (morning proactive
    check-in) queries "expired yesterday/today" off this same table.
    """

    __tablename__ = "user_temporary_restrictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_pattern: Mapped[MovementPattern] = mapped_column(
        enum_column(MovementPattern, "movement_pattern"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Set at creation to today + DEFAULT_RESTRICTION_DAYS (see
    # UserTemporaryRestrictionService), extended in place on a repeat
    # report for the same pattern rather than creating a duplicate row.
    expires_at: Mapped[date_] = mapped_column(Date, nullable=False)
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
