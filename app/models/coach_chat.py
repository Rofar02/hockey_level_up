import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column


class CoachChatRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class CoachChatMessage(Base):
    """One turn of the AI coach conversation (POST /users/me/coach-chat).
    Doubles as both the dialogue-context source (last ~10 messages replayed
    to Claude) and the monthly rate-limit counter (COUNT of role='user' rows
    with created_at in the current calendar month -- see
    CoachChatRepository.count_user_messages_this_month)."""

    __tablename__ = "coach_chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[CoachChatRole] = mapped_column(
        enum_column(CoachChatRole, "coach_chat_role"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Client-side `default` (not just `server_default`) is deliberate: a
    # single send_message call inserts the user turn and the assistant
    # turn in the same transaction, and Postgres's now() is frozen for the
    # whole transaction -- two func.now()-only rows would tie on
    # created_at and sort unpredictably. datetime.now() at the Python
    # level gives each row its own, later timestamp instead.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
