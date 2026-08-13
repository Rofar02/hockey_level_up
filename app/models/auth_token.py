import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column


class AuthTokenPurpose(enum.StrEnum):
    EMAIL_VERIFY = "email_verify"
    PASSWORD_RESET = "password_reset"


class AuthToken(Base):
    """One-time, expiring tokens for the email-verify/password-reset flows --
    deliberately NOT built on the JWT access/refresh mechanism in
    app/core/security.py: those are stateless by design (anyone holding a
    valid signature is trusted for the token's whole life, no DB round trip,
    no way to revoke early), while these need server-side single-use
    enforcement (used_at) and a purpose-specific TTL, which requires a row to
    check against.

    The raw token (secrets.token_urlsafe(32), see AuthTokenService) only
    ever exists in the email sent to the user and the request that redeems
    it -- only its SHA-256 hex digest is stored in token_hash, so a DB read
    (backup, replication lag exposure, leaked dump) can never itself be
    used to claim the token, unlike storing it raw would allow.
    """

    __tablename__ = "auth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256 hex digest is always exactly 64 chars.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    purpose: Mapped[AuthTokenPurpose] = mapped_column(
        enum_column(AuthTokenPurpose, "auth_token_purpose"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
