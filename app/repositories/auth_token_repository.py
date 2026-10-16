import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_token import AuthToken, AuthTokenPurpose


class AuthTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        purpose: AuthTokenPurpose,
        expires_at: datetime,
    ) -> AuthToken:
        token = AuthToken(
            user_id=user_id, token_hash=token_hash, purpose=purpose, expires_at=expires_at
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_hash(self, token_hash: str, *, for_update: bool = False) -> AuthToken | None:
        # token_hash is globally unique regardless of purpose (see the
        # model) -- callers compare .purpose themselves against what they
        # expected, rather than filtering it into this query, so a token
        # redeemed at the wrong endpoint is "invalid" like any other
        # mismatch, not a separate lookup path.
        query = select(AuthToken).where(AuthToken.token_hash == token_hash)
        if for_update:
            # Two clicks on one link at once: the second waits here and then
            # sees used_at already set (А8, 2026-10-13).
            query = query.with_for_update()
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def spend_unused(self, user_id: uuid.UUID, purpose: AuthTokenPurpose, now: datetime) -> None:
        """Marks every still-unused token of this purpose as used -- after a
        password change no older reset link may set it again."""
        await self._session.execute(
            update(AuthToken)
            .where(AuthToken.user_id == user_id, AuthToken.purpose == purpose, AuthToken.used_at.is_(None))
            .values(used_at=now)
        )
