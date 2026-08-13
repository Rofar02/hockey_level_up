"""AuthTokenService: one-time, expiring tokens behind email-verify/
password-reset (see app/models/auth_token.py for why this is a separate
mechanism from the JWT access/refresh tokens).

Covers: happy-path create->consume round trip, expiry, single-use
(a second consume of the same raw token fails even though the first
succeeded), an unknown/garbage token, and redeeming a token at the wrong
purpose (created for one flow, presented to the other).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.auth_token import AuthTokenPurpose
from app.models.user import User
from app.services.auth_token_service import AuthTokenService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"tok_{unique}",
        email=f"tok_{unique}@example.com",
        password_hash="irrelevant",
    )
    defaults.update(overrides)
    return User(**defaults)


@pytest.mark.asyncio
async def test_create_then_consume_round_trip(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = AuthTokenService(db_session)
    raw_token = await service.create_token(user.id, AuthTokenPurpose.EMAIL_VERIFY)
    redeemed_user = await service.consume_token(raw_token, AuthTokenPurpose.EMAIL_VERIFY)

    assert redeemed_user.id == user.id


@pytest.mark.asyncio
async def test_raw_token_is_never_stored_in_the_clear(db_session) -> None:
    from sqlalchemy import select

    from app.models.auth_token import AuthToken

    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    raw_token = await AuthTokenService(db_session).create_token(user.id, AuthTokenPurpose.EMAIL_VERIFY)

    row = (await db_session.execute(select(AuthToken).where(AuthToken.user_id == user.id))).scalar_one()
    assert row.token_hash != raw_token
    assert raw_token not in row.token_hash


@pytest.mark.asyncio
async def test_reusing_a_consumed_token_fails(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = AuthTokenService(db_session)
    raw_token = await service.create_token(user.id, AuthTokenPurpose.EMAIL_VERIFY)
    await service.consume_token(raw_token, AuthTokenPurpose.EMAIL_VERIFY)

    with pytest.raises(HTTPException) as exc_info:
        await service.consume_token(raw_token, AuthTokenPurpose.EMAIL_VERIFY)
    assert exc_info.value.status_code == 410


@pytest.mark.asyncio
async def test_expired_token_is_rejected(db_session) -> None:
    from app.models.auth_token import AuthToken
    from app.services.auth_token_service import _hash_token

    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    raw_token = "expired-raw-token"
    db_session.add(
        AuthToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            purpose=AuthTokenPurpose.EMAIL_VERIFY,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await AuthTokenService(db_session).consume_token(raw_token, AuthTokenPurpose.EMAIL_VERIFY)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_unknown_token_is_rejected(db_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await AuthTokenService(db_session).consume_token(
            "this-token-was-never-issued", AuthTokenPurpose.EMAIL_VERIFY
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_wrong_purpose_is_rejected(db_session) -> None:
    """A password-reset token presented at the email-verify endpoint (or
    vice versa) must not validate just because the hash matches -- purpose
    is part of what's being checked, not just existence/expiry."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = AuthTokenService(db_session)
    raw_token = await service.create_token(user.id, AuthTokenPurpose.PASSWORD_RESET)

    with pytest.raises(HTTPException) as exc_info:
        await service.consume_token(raw_token, AuthTokenPurpose.EMAIL_VERIFY)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_email_verify_and_password_reset_have_different_ttls(db_session) -> None:
    from sqlalchemy import select

    from app.models.auth_token import AuthToken

    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = AuthTokenService(db_session)
    await service.create_token(user.id, AuthTokenPurpose.EMAIL_VERIFY)
    await service.create_token(user.id, AuthTokenPurpose.PASSWORD_RESET)

    rows = {
        row.purpose: row.expires_at
        for row in (
            await db_session.execute(select(AuthToken).where(AuthToken.user_id == user.id))
        ).scalars()
    }
    verify_ttl = rows[AuthTokenPurpose.EMAIL_VERIFY] - datetime.now(timezone.utc)
    reset_ttl = rows[AuthTokenPurpose.PASSWORD_RESET] - datetime.now(timezone.utc)
    # Upper bounds are <=, not < -- expires_at is computed once at
    # create_token time, so re-measuring "now" here can land exactly on (but
    # never past) the original TTL if this assertion runs fast enough,
    # which a strict < flakes on.
    assert timedelta(hours=47) < verify_ttl <= timedelta(hours=48)
    assert timedelta(minutes=59) < reset_ttl <= timedelta(hours=1)
