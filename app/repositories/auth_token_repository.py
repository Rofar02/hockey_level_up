import uuid
from datetime import datetime

from sqlalchemy import select
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

    async def get_by_hash(self, token_hash: str) -> AuthToken | None:
        # token_hash is globally unique regardless of purpose (see the
        # model) -- callers compare .purpose themselves against what they
        # expected, rather than filtering it into this query, so a token
        # redeemed at the wrong endpoint is "invalid" like any other
        # mismatch, not a separate lookup path.
        result = await self._session.execute(
            select(AuthToken).where(AuthToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()
