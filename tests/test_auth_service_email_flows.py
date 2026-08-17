"""AuthService's email-verification and password-reset flows.

Covers exactly the guarantees called out in the design: registration must
never fail because email delivery failed (a real risk the first time this
project ever sends email), new accounts start unverified while pre-existing
ones were backfilled to verified (see the migration -- checked here only for
*newly registered* accounts, which is this service's own responsibility),
password-reset/request is a hard 503 with no RESEND_API_KEY (checked before
any user lookup, so it can't leak account existence), and its response is
byte-identical for an existing vs a nonexistent email.
"""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import Settings
from app.models.auth_token import AuthTokenPurpose
from app.models.user import User
from app.schemas.auth import PasswordResetRequest
from app.schemas.user import UserCreate
from app.services import auth_service
from app.services.auth_service import AuthService
from app.services.auth_token_service import AuthTokenService
from app.services.email_service import EmailService


def _settings_with_resend_key(key: str | None) -> Settings:
    return Settings(resend_api_key=key)


def _register_payload(**overrides) -> UserCreate:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        email=f"reg_{unique}@example.com",
        password="password123",
        last_name="Test",
        first_name="User",
        jersey_number=7,
        privacy_consent=True,
    )
    defaults.update(overrides)
    return UserCreate(**defaults)


def _install_fake_verification_send(monkeypatch):
    """Replaces EmailService.send_verification_email with a fake that
    records exactly what it was called with -- no real Resend call, ever,
    same convention as CoachChatService tests fake _call_anthropic."""
    captured: dict = {}

    async def _fake(self, user, raw_token):  # noqa: ANN001 -- mirrors bound method signature
        captured["user_id"] = user.id
        captured["raw_token"] = raw_token

    monkeypatch.setattr(EmailService, "send_verification_email", _fake)
    return captured


def _install_failing_verification_send(monkeypatch):
    async def _boom(self, user, raw_token):  # noqa: ANN001
        raise RuntimeError("Resend is down")

    monkeypatch.setattr(EmailService, "send_verification_email", _boom)


def _install_fake_reset_send(monkeypatch):
    captured: dict = {}

    async def _fake(self, user, raw_token):  # noqa: ANN001
        captured["user_id"] = user.id
        captured["raw_token"] = raw_token

    monkeypatch.setattr(EmailService, "send_password_reset_email", _fake)
    return captured


def _fail_if_reset_send_called(monkeypatch):
    async def _boom(self, user, raw_token):  # noqa: ANN001
        raise AssertionError("send_password_reset_email must not be called")

    monkeypatch.setattr(EmailService, "send_password_reset_email", _boom)


# -- register() --


@pytest.mark.asyncio
async def test_register_creates_unverified_user(db_session, monkeypatch) -> None:
    _install_fake_verification_send(monkeypatch)

    user = await AuthService(db_session).register(_register_payload())

    assert user.email_verified is False


@pytest.mark.asyncio
async def test_register_sends_a_working_verification_token(db_session, monkeypatch) -> None:
    captured = _install_fake_verification_send(monkeypatch)

    user = await AuthService(db_session).register(_register_payload())

    assert captured["user_id"] == user.id
    redeemed = await AuthTokenService(db_session).consume_token(
        captured["raw_token"], AuthTokenPurpose.EMAIL_VERIFY
    )
    assert redeemed.id == user.id


@pytest.mark.asyncio
async def test_register_survives_email_send_failure(db_session, monkeypatch) -> None:
    _install_failing_verification_send(monkeypatch)
    payload = _register_payload()

    user = await AuthService(db_session).register(payload)

    assert user.email_verified is False
    stored = (
        await db_session.execute(select(User).where(User.id == user.id))
    ).scalar_one_or_none()
    assert stored is not None
    assert stored.email == payload.email


# -- resend_verification_email() --


@pytest.mark.asyncio
async def test_resend_refuses_when_already_verified(db_session, monkeypatch) -> None:
    _install_fake_verification_send(monkeypatch)
    user = await AuthService(db_session).register(_register_payload())
    user.email_verified = True
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await AuthService(db_session).resend_verification_email(user)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_resend_raises_clear_error_on_send_failure(db_session, monkeypatch) -> None:
    # Unlike register()'s and request_password_reset()'s best-effort sends
    # (both must survive a delivery failure silently), this is the one
    # send the caller is directly waiting on -- a Resend failure here must
    # surface as a clean, translated error, not an opaque 500.
    _install_fake_verification_send(monkeypatch)
    user = await AuthService(db_session).register(_register_payload())

    _install_failing_verification_send(monkeypatch)
    with pytest.raises(HTTPException) as exc_info:
        await AuthService(db_session).resend_verification_email(user)
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_resend_issues_a_fresh_token(db_session, monkeypatch) -> None:
    first_capture = _install_fake_verification_send(monkeypatch)
    user = await AuthService(db_session).register(_register_payload())
    first_token = first_capture["raw_token"]

    second_capture = _install_fake_verification_send(monkeypatch)
    await AuthService(db_session).resend_verification_email(user)

    assert second_capture["raw_token"] != first_token
    redeemed = await AuthTokenService(db_session).consume_token(
        second_capture["raw_token"], AuthTokenPurpose.EMAIL_VERIFY
    )
    assert redeemed.id == user.id


# -- confirm_email_verification() --


@pytest.mark.asyncio
async def test_confirm_email_verification_flips_the_flag(db_session, monkeypatch) -> None:
    captured = _install_fake_verification_send(monkeypatch)
    user = await AuthService(db_session).register(_register_payload())
    assert user.email_verified is False

    verified_user = await AuthService(db_session).confirm_email_verification(captured["raw_token"])

    assert verified_user.id == user.id
    assert verified_user.email_verified is True


# -- request_password_reset() --


@pytest.mark.asyncio
async def test_password_reset_request_503s_without_a_resend_key(db_session, monkeypatch) -> None:
    monkeypatch.setattr(auth_service, "get_settings", lambda: _settings_with_resend_key(None))
    _fail_if_reset_send_called(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        await AuthService(db_session).request_password_reset("whoever@example.com")
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_password_reset_request_503s_even_for_a_real_registered_email(
    db_session, monkeypatch
) -> None:
    """The 503 gate runs before the user lookup -- must fire identically
    whether or not the email is actually registered, otherwise its mere
    presence/absence would leak account existence."""
    monkeypatch.setattr(auth_service, "get_settings", lambda: _settings_with_resend_key(None))
    _fail_if_reset_send_called(monkeypatch)
    _install_fake_verification_send(monkeypatch)
    payload = _register_payload()
    await AuthService(db_session).register(payload)

    with pytest.raises(HTTPException) as exc_info:
        await AuthService(db_session).request_password_reset(payload.email)
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_password_reset_request_sends_for_a_real_email(db_session, monkeypatch) -> None:
    monkeypatch.setattr(auth_service, "get_settings", lambda: _settings_with_resend_key("test-key"))
    _install_fake_verification_send(monkeypatch)
    user = await AuthService(db_session).register(_register_payload())
    captured = _install_fake_reset_send(monkeypatch)

    await AuthService(db_session).request_password_reset(user.email)

    assert captured["user_id"] == user.id
    redeemed = await AuthTokenService(db_session).consume_token(
        captured["raw_token"], AuthTokenPurpose.PASSWORD_RESET
    )
    assert redeemed.id == user.id


@pytest.mark.asyncio
async def test_password_reset_request_is_a_silent_noop_for_unknown_email(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(auth_service, "get_settings", lambda: _settings_with_resend_key("test-key"))
    _fail_if_reset_send_called(monkeypatch)

    # No exception, no email sent -- request_password_reset itself returns
    # None either way, this just proves the "unknown email" branch never
    # reaches EmailService at all.
    await AuthService(db_session).request_password_reset("nobody-registered-with-this@example.com")


@pytest.mark.asyncio
async def test_password_reset_request_response_is_identical_for_known_and_unknown_email(
    db_session, monkeypatch
) -> None:
    """Router-level check: POST /auth/password-reset/request must return the
    exact same body for a real account and a made-up email -- a byte-level
    diff, not just "both succeeded"."""
    from app.routers.auth import request_password_reset as request_password_reset_endpoint

    monkeypatch.setattr(auth_service, "get_settings", lambda: _settings_with_resend_key("test-key"))
    _install_fake_reset_send(monkeypatch)
    _install_fake_verification_send(monkeypatch)
    payload = _register_payload()
    user = await AuthService(db_session).register(payload)

    known_response = await request_password_reset_endpoint(
        PasswordResetRequest(email=user.email), db_session
    )
    unknown_response = await request_password_reset_endpoint(
        PasswordResetRequest(email="definitely-not-registered@example.com"), db_session
    )

    assert known_response.model_dump() == unknown_response.model_dump()


# -- confirm_password_reset() --


@pytest.mark.asyncio
async def test_confirm_password_reset_updates_the_password_hash(db_session, monkeypatch) -> None:
    from app.core.security import verify_password

    monkeypatch.setattr(auth_service, "get_settings", lambda: _settings_with_resend_key("test-key"))
    _install_fake_verification_send(monkeypatch)
    payload = _register_payload()
    user = await AuthService(db_session).register(payload)
    old_hash = user.password_hash

    captured = _install_fake_reset_send(monkeypatch)
    await AuthService(db_session).request_password_reset(user.email)

    await AuthService(db_session).confirm_password_reset(captured["raw_token"], "brand-new-password1")

    assert user.password_hash != old_hash
    assert verify_password("brand-new-password1", user.password_hash)


@pytest.mark.asyncio
async def test_confirm_password_reset_token_is_single_use(db_session, monkeypatch) -> None:
    monkeypatch.setattr(auth_service, "get_settings", lambda: _settings_with_resend_key("test-key"))
    _install_fake_verification_send(monkeypatch)
    payload = _register_payload()
    user = await AuthService(db_session).register(payload)

    captured = _install_fake_reset_send(monkeypatch)
    await AuthService(db_session).request_password_reset(user.email)

    service = AuthService(db_session)
    await service.confirm_password_reset(captured["raw_token"], "first-new-password1")

    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_password_reset(captured["raw_token"], "second-new-password1")
    assert exc_info.value.status_code == 410
