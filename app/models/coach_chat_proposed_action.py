import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column


class CoachActionType(enum.StrEnum):
    """What the coach chat is proposing -- each value maps to exactly one
    existing, already-validated service method it dispatches to on
    confirmation (CoachChatActionService), never a new write path:
    SKILL_PRIORITY_ADD -> SkillService.replace_user_preferences,
    SET_TOURNAMENT_DATE -> UserService.update_profile,
    REPORT_RESTRICTION -> UserTemporaryRestrictionService.report."""

    SKILL_PRIORITY_ADD = "skill_priority_add"
    SET_TOURNAMENT_DATE = "set_tournament_date"
    REPORT_RESTRICTION = "report_restriction"


class CoachActionStatus(enum.StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class CoachChatProposedAction(Base):
    """An action the AI coach proposed in one chat reply (parsed from that
    reply's trailing <!--ACTION:{...}--> marker, see
    CoachChatService._extract_proposed_action) -- never applied by the model
    itself, only after the player explicitly confirms via
    POST /users/me/coach-chat/actions/{id}/confirm, which re-validates and
    dispatches to the real service method for `action_type`.

    Only one PENDING row per user at a time: creating a new one marks any
    prior PENDING row EXPIRED first (see CoachChatService), so a stale
    proposal from an earlier part of the conversation can't get confirmed
    against a since-moved-on context. No background job needed for this --
    expiry only ever happens as a side effect of a new proposal being made.
    """

    __tablename__ = "coach_chat_proposed_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("coach_chat_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_type: Mapped[CoachActionType] = mapped_column(
        enum_column(CoachActionType, "coach_action_type"), nullable=False
    )
    # Type-specific data, e.g. {"skill_id": "..."} or {"tournament_date":
    # "2027-03-15"} -- validated against a strict per-action_type Pydantic
    # model at creation time (see coach_chat_service.py), never trusted
    # as-is at confirm time either (the dispatched service method re-runs
    # its own full validation regardless).
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[CoachActionStatus] = mapped_column(
        enum_column(CoachActionStatus, "coach_action_status"),
        nullable=False,
        default=CoachActionStatus.PENDING,
        server_default=CoachActionStatus.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
