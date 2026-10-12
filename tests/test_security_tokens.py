"""JWT handling on PyJWT (step 8, security, 3): fixed algorithm, expiry,
token type."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from jwt import ExpiredSignatureError, InvalidTokenError

from app.core.config import get_settings
from app.core.security import TokenType, create_access_token, create_refresh_token, decode_token

settings = get_settings()


def _encode(payload: dict, *, key: str | None = None, algorithm: str = "HS256") -> str:
    return jwt.encode(payload, key or settings.jwt_secret_key, algorithm=algorithm)


def _payload(**extra) -> dict:
    now = datetime.now(timezone.utc)
    return {"sub": "abc", "type": "access", "iat": now, "exp": now + timedelta(minutes=5), **extra}


def test_round_trip() -> None:
    assert decode_token(create_access_token("abc"), TokenType.ACCESS) == "abc"
    assert decode_token(create_refresh_token("abc"), TokenType.REFRESH) == "abc"


def test_wrong_type_is_refused() -> None:
    with pytest.raises(InvalidTokenError):
        decode_token(create_refresh_token("abc"), TokenType.ACCESS)


def test_expired_is_refused() -> None:
    token = _encode(_payload(exp=datetime.now(timezone.utc) - timedelta(seconds=1)))
    with pytest.raises(ExpiredSignatureError):
        decode_token(token, TokenType.ACCESS)


def test_foreign_key_and_unsigned_tokens_are_refused() -> None:
    with pytest.raises(InvalidTokenError):
        decode_token(_encode(_payload(), key="x" * 40), TokenType.ACCESS)
    with pytest.raises(InvalidTokenError):
        decode_token(jwt.encode(_payload(), None, algorithm="none"), TokenType.ACCESS)


def test_token_without_expiry_is_refused() -> None:
    payload = _payload()
    del payload["exp"]
    with pytest.raises(InvalidTokenError):
        decode_token(_encode(payload), TokenType.ACCESS)
