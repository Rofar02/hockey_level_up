import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column


class SetFeedback(enum.StrEnum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    MAX = "max"


class SetCompletion(Base):
    """Per-set logging, layered on top of SessionBlock.completed_at.

    This is additional granularity, not a replacement: block_completed (see
    app/events/handlers/block_completed.py) still fires once per exercise
    from SessionBlock, and stat/XP gain is still computed from
    difficulty_level there, untouched by anything in this table.
    """

    __tablename__ = "set_completions"
    __table_args__ = (
        # set_number resets per exercise-in-session, so uniqueness is scoped
        # to (training_session_id, exercise_id) rather than just set_number.
        UniqueConstraint(
            "training_session_id",
            "exercise_id",
            "set_number",
            name="uq_set_completions_session_exercise_set",
        ),
        CheckConstraint("set_number >= 1", name="ck_set_completions_set_number_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # No ondelete, matching SessionBlock.exercise_id -- exercises are curated
    # content, deleting one that has logged history should fail loudly
    # rather than silently wipe a user's set log (see
    # ExerciseService.delete_exercise's existing 409-on-IntegrityError).
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercises.id"), nullable=False, index=True
    )
    training_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    reps_completed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds_completed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    was_weight_adjusted_manually: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Only ever set on the row for an exercise's last logged set within a
    # session -- see SetCompletionService.save_feedback. Every other row's
    # feedback stays null.
    feedback: Mapped[SetFeedback | None] = mapped_column(
        enum_column(SetFeedback, "set_feedback"), nullable=True
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
