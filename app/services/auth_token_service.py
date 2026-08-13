import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_token import AuthTokenPurpose
from app.models.user import User
from app.repositories.auth_token_repository import AuthTokenRepository
from app.repositories.user_repository import UserRepository

# How long a raw token is redeemable for, per purpose -- password reset is
# short-lived (a live security window someone could act on if an inbox is
# compromised), email verification is long-lived (no security window to
# minimize, just needs to survive someone reading their email a day or two
# late).
TOKEN_TTL: dict[AuthTokenPurpose, timedelta] = {
    AuthTokenPurpose.EMAIL_VERIFY: timedelta(hours=48),
    AuthTokenPurpose.PASSWORD_RESET: timedelta(hours=1),
}

_RAW_TOKEN_BYTES = 32


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class AuthTokenService:
    """Create/redeem one-time AuthToken rows -- see that model's docstring
    for why this exists instead of reusing the JWT access/refresh mechanism.

    Neither method commits: create_token is always called as part of a
    larger flow (send an email, then persist state) that the caller commits
    once as a unit, and consume_token's own used_at write must land in the
    same transaction as whatever the caller does with the token (mark email
    verified / change the password) -- committing here would let one
    succeed without the other if the caller's own write then failed.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tokens = AuthTokenRepository(session)
        self._users = UserRepository(session)

    async def create_token(self, user_id: uuid.UUID, purpose: AuthTokenPurpose) -> str:
        raw_token = secrets.token_urlsafe(_RAW_TOKEN_BYTES)
        expires_at = datetime.now(timezone.utc) + TOKEN_TTL[purpose]
        await self._tokens.create(user_id, _hash_token(raw_token), purpose, expires_at)
        return raw_token

    async def consume_token(self, raw_token: str, expected_purpose: AuthTokenPurpose) -> User:
        """Validates raw_token for expected_purpose, marks it used, and
        returns the owning User -- or raises a specific HTTPException:

          - 400 if no such token exists, or it exists for a different
            purpose (redeeming a password-reset link at the email-verify
            endpoint, say) -- both look identical to the caller, "not a
            valid token for what you're trying to do".
          - 410 if it was already redeemed once before -- a distinct status
            from "never existed", since the link itself was genuine, it's
            just spent (mirrors push_service's use of 410 for "no longer
            valid", not "invalid").
          - 400 if it's past expires_at.
        """
        token = await self._tokens.get_by_hash(_hash_token(raw_token))
        if token is None or token.purpose != expected_purpose:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Ссылка недействительна"
            )
        if token.used_at is not None:
            raise HTTPException(
                status_code=status.HTTP_410_GONE, detail="Ссылка уже была использована"
            )
        if token.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Срок действия ссылки истёк"
            )

        token.used_at = datetime.now(timezone.utc)
        user = await self._users.get_by_id(token.user_id)
        if user is None:
            # Not reachable in practice (user_id FKs to users with CASCADE,
            # so the token would have been deleted with the user) -- guards
            # against ever returning None to a caller typed to expect User.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Ссылка недействительна"
            )
        return user
