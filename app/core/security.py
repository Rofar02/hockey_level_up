import asyncio
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


# bcrypt is deliberately slow (~0.3-0.4 s of pure CPU per call) and releases
# the GIL, so request handlers run it in a worker thread. Called inline, it
# froze the whole event loop for every login/registration -- found in a
# 2026-09-28 load test: 20 concurrent players pushed login to 2 s and week
# generation to 10 s, with the database idle the whole time.
async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain_password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(verify_password, plain_password, password_hash)


def _create_token(subject: str, token_type: TokenType, expires_delta: timedelta, **claims: Any) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
        **claims,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, version: int = 0) -> str:
    return _create_token(
        subject,
        TokenType.ACCESS,
        timedelta(minutes=settings.access_token_expire_minutes),
        ver=version,
    )


def create_refresh_token(subject: str, version: int, session_id: str, jti: str) -> str:
    """`session_id`/`jti` point at the device's RefreshSession row -- see
    AuthService.refresh for the rotation."""
    return _create_token(
        subject,
        TokenType.REFRESH,
        timedelta(days=settings.refresh_token_expire_days),
        ver=version,
        sid=session_id,
        jti=jti,
    )


def decode_claims(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Return the verified claims, or raise InvalidTokenError if invalid,
    expired (ExpiredSignatureError is a subclass) or of the wrong type.
    The algorithm list is fixed -- never taken from the token header."""
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub", "type"]},
    )
    if payload.get("type") != expected_type.value:
        raise InvalidTokenError("Unexpected token type")
    if not isinstance(payload.get("sub"), str):
        raise InvalidTokenError("Token missing subject")
    return payload


def decode_token(token: str, expected_type: TokenType) -> str:
    """The subject of a verified token, see decode_claims."""
    return decode_claims(token, expected_type)["sub"]


def token_version(claims: dict[str, Any]) -> int:
    """Tokens issued before step 8 carry no "ver" -- they count as version 0,
    so they keep working until the player's first version bump."""
    version = claims.get("ver", 0)
    return version if isinstance(version, int) else -1
