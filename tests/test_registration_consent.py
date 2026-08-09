"""152-FZ privacy consent gate on registration: AuthService.register must
reject a request that doesn't explicitly opt in (missing or false), and must
stamp User.privacy_consent_at the moment it does.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.schemas.user import UserCreate
from app.services.auth_service import AuthService


def _make_payload(*, privacy_consent: bool | None) -> UserCreate:
    unique = uuid.uuid4().hex[:8]
    kwargs = dict(
        email=f"consent_{unique}@example.com",
        password="password123",
        last_name="Test",
        first_name="User",
        jersey_number=77,
    )
    if privacy_consent is not None:
        kwargs["privacy_consent"] = privacy_consent
    return UserCreate(**kwargs)


@pytest.mark.asyncio
async def test_register_without_consent_field_returns_400(db_session) -> None:
    payload = _make_payload(privacy_consent=None)  # field omitted -> defaults to False

    with pytest.raises(HTTPException) as exc_info:
        await AuthService(db_session).register(payload)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_register_with_explicit_false_consent_returns_400(db_session) -> None:
    payload = _make_payload(privacy_consent=False)

    with pytest.raises(HTTPException) as exc_info:
        await AuthService(db_session).register(payload)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_register_with_consent_sets_privacy_consent_at(db_session) -> None:
    payload = _make_payload(privacy_consent=True)
    before = datetime.now(timezone.utc) - timedelta(seconds=5)

    user = await AuthService(db_session).register(payload)

    after = datetime.now(timezone.utc) + timedelta(seconds=5)
    assert user.privacy_consent_at is not None
    assert before <= user.privacy_consent_at <= after


@pytest.mark.asyncio
async def test_register_generates_a_unique_username(db_session) -> None:
    # Registration no longer collects a username from the client -- it's
    # generated server-side (still required as a unique, non-null column
    # for pre-existing accounts' login-by-username to keep working).
    payload_a = _make_payload(privacy_consent=True)
    payload_b = _make_payload(privacy_consent=True)

    user_a = await AuthService(db_session).register(payload_a)
    user_b = await AuthService(db_session).register(payload_b)

    assert user_a.username != ""
    assert user_a.username != user_b.username
