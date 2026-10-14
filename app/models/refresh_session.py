import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RefreshSession(Base):
    """One signed-in device (step 8, security, 2). Its refresh token carries
    the row id ("sid") and the current jti; each /auth/refresh swaps in a
    new jti, so a used refresh token stops working. The previous jti stays
    good until the new one is used -- two tabs or a retried request on a bad
    network may send the same token again -- and any older one ends the
    session (a stolen token was used). Signing out of this device deletes
    the row; signing out everywhere deletes them all and bumps
    users.token_version."""

    __tablename__ = "refresh_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    current_jti: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_jti: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
