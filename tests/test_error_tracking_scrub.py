"""No passwords or tokens in error reports (2026-10-13, А3): an exception
in the middle of a password change reaches GlitchTip without the passwords,
and no token survives anywhere in the event as plain text."""
import json
import uuid

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from app.core.config import Settings
from app.core.error_tracking import FILTERED, scrub_text, sentry_options
from app.core.security import hash_password
from app.models.user import User
from app.schemas.auth import PasswordChange, RefreshRequest
from app.services import auth_service
from app.services.auth_service import AuthService

OLD_PASSWORD = "OldSecret-111"
NEW_PASSWORD = "NewSecret-222"


class _CaptureTransport(Transport):
    def __init__(self, options=None) -> None:
        super().__init__(options)
        self.events: list[dict] = []

    def capture_envelope(self, envelope) -> None:
        for item in envelope.items:
            if item.headers.get("type") == "event":
                self.events.append(json.loads(item.payload.get_bytes()))


@pytest.fixture
def captured():
    settings = Settings(glitchtip_dsn="http://public@glitchtip.invalid/1", environment="test")
    transport = _CaptureTransport()
    sentry_sdk.init(**{**sentry_options(settings), "transport": transport})
    try:
        yield transport
    finally:
        sentry_sdk.init(dsn=None)


def test_scrub_text_hides_jwts_and_key_values() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abcDEF123_-x"
    text = f"bad header Bearer {jwt}; body password={OLD_PASSWORD}&x=1 {{'refresh_token': 'r-abc'}}"
    scrubbed = scrub_text(text)
    assert jwt not in scrubbed
    assert OLD_PASSWORD not in scrubbed
    assert "r-abc" not in scrubbed
    assert FILTERED in scrubbed
    assert "x=1" in scrubbed


def test_secret_fields_stay_out_of_repr() -> None:
    change = PasswordChange(current_password=OLD_PASSWORD, new_password=NEW_PASSWORD)
    assert OLD_PASSWORD not in repr(change) and NEW_PASSWORD not in repr(change)
    assert "r-abc" not in repr(RefreshRequest(refresh_token="r-abc"))


@pytest.mark.asyncio
async def test_crash_inside_a_password_change_reports_no_secrets(db_session, monkeypatch, captured) -> None:
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"scrub_{unique}",
        email=f"scrub_{unique}@example.com",
        password_hash=hash_password(OLD_PASSWORD),
        timezone="UTC",
    )
    db_session.add(user)
    await db_session.flush()
    service = AuthService(db_session)
    pair = await service.login(user.username, OLD_PASSWORD)

    async def _boom(password: str) -> str:
        payload = PasswordChange(current_password=OLD_PASSWORD, new_password=password)
        raise RuntimeError(f"hashing failed for {payload!r}, password={password}, token={pair.access_token}")

    monkeypatch.setattr(auth_service, "hash_password_async", _boom)
    try:
        await service.change_password(user, OLD_PASSWORD, NEW_PASSWORD)
    except RuntimeError as exc:
        sentry_sdk.capture_exception(exc)
    sentry_sdk.flush()

    assert len(captured.events) == 1
    dumped = json.dumps(captured.events[0], ensure_ascii=False)
    for secret in (OLD_PASSWORD, NEW_PASSWORD, pair.access_token, pair.refresh_token):
        assert secret not in dumped
    assert "hashing failed" in dumped
    # No stack-frame locals at all.
    for exception in captured.events[0]["exception"]["values"]:
        for frame in exception.get("stacktrace", {}).get("frames", []):
            assert "vars" not in frame
