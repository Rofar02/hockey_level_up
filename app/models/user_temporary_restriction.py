import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column
from app.models.exercise import MovementPattern, MuscleGroup


class UserTemporaryRestriction(Base):
    """A player-reported "this hurts right now" flag -- excludes matching
    exercises from assembly (MAIN, warmup, cooldown, GAME activation, party
    suggestions -- everywhere, see ExerciseRepository.list_for_assembly)
    for as long as it's active.

    Exactly one of `movement_pattern` / `muscle_group` is set, never both,
    never neither (see the CHECK constraint below) -- two independent entry
    points into the same restriction concept, added 2026-08-27 alongside
    RestrictionsPage's body-avatar picker (reuses the muscle-load heatmap's
    `body-muscles` integration): tapping an anatomical region on the avatar
    reports a `muscle_group` directly (exact match against
    ExerciseMuscleGroup, the same "presence, not weight" tagging
    ScheduleService._apply_muscle_balance already reads for muscle
    balancing -- more precise than approximating a body part into one of
    the coarser movement-pattern buckets), while the handful of concerns
    with no single body location (rotation, coordination, stick-handling)
    still report a `movement_pattern`, unchanged from the original P3 item
    #7 shape.

    Manual report only for now (P3 item #7, first pass) -- a player
    messages the coach and an AI classifies the free text into a pattern
    or muscle group is a later layer on top of this same table, not built
    yet.

    Active = expires_at >= today AND lifted_at IS NULL. Expired/lifted
    rows are kept, not deleted -- the morning proactive check-in job
    (app/services/checkin_scheduler.py) queries "expired yesterday/today,
    not yet checked in" off this same table via `checkin_sent_at`.
    """

    __tablename__ = "user_temporary_restrictions"
    __table_args__ = (
        CheckConstraint(
            "(movement_pattern IS NOT NULL) <> (muscle_group IS NOT NULL)",
            name="ck_user_temporary_restrictions_exactly_one_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_pattern: Mapped[MovementPattern | None] = mapped_column(
        enum_column(MovementPattern, "movement_pattern"), nullable=True
    )
    muscle_group: Mapped[MuscleGroup | None] = mapped_column(
        enum_column(MuscleGroup, "muscle_group"), nullable=True
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
    # Idempotency guard for checkin_scheduler, same role as
    # DayPlan.reminder_sent_at -- set once the morning check-in push has
    # gone out for this row, never reset (a lifted-early restriction still
    # counts as "already checked in" if it already got one).
    checkin_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
