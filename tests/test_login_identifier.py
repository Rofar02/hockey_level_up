"""AuthService.authenticate must accept either the username or the email as
the login identifier -- new accounts have no client-chosen username (see
AuthService._generate_username), so they can only log in by email, while
pre-existing accounts still expect their username to work.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.core.security import hash_password
from app.models.user import User
from app.services.auth_service import AuthService

PASSWORD = "correct-horse-battery"


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"login_{unique}",
        email=f"login_{unique}@example.com",
        password_hash=hash_password(PASSWORD),
    )


@pytest.mark.asyncio
async def test_authenticate_with_username_succeeds(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    authenticated = await AuthService(db_session).authenticate(user.username, PASSWORD)

    assert authenticated.id == user.id


@pytest.mark.asyncio
async def test_authenticate_with_email_succeeds(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    authenticated = await AuthService(db_session).authenticate(user.email, PASSWORD)

    assert authenticated.id == user.id


@pytest.mark.asyncio
async def test_authenticate_with_wrong_password_returns_401(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await AuthService(db_session).authenticate(user.email, "not-the-password")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticate_with_unknown_identifier_returns_401(db_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await AuthService(db_session).authenticate("nobody@example.com", PASSWORD)

    assert exc_info.value.status_code == 401
