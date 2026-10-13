"""Token revocation (step 8, security, 2): a version in every token, one
refresh session per device, rotation with a short grace for repeats."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.auth_token import AuthTokenPurpose
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.routers.deps import get_current_user
from app.services import auth_service
from app.services.auth_service import AuthService
from app.services.auth_token_service import AuthTokenService

PASSWORD = "password123"


async def _user(db_session) -> User:
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"tok_{unique}",
        email=f"tok_{unique}@example.com",
        password_hash=hash_password(PASSWORD),
        timezone="UTC",
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _assert_401(coro) -> None:
    with pytest.raises(HTTPException) as exc:
        await coro
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_a_used_refresh_token_dies_after_the_grace(db_session, monkeypatch) -> None:
    user = await _user(db_session)
    service = AuthService(db_session)
    first = await service.login(user.username, PASSWORD)

    second = await service.refresh(first.refresh_token)
    # A repeat right away (two tabs, a retry) still works ...
    again = await service.refresh(first.refresh_token)
    assert again.refresh_token != first.refresh_token

    # ... later on it is a stolen copy: the device's session ends.
    monkeypatch.setattr(auth_service, "REFRESH_REUSE_GRACE", timedelta(seconds=-1))
    await _assert_401(service.refresh(first.refresh_token))
    await _assert_401(service.refresh(second.refresh_token))


@pytest.mark.asyncio
async def test_rotation_keeps_going(db_session) -> None:
    user = await _user(db_session)
    service = AuthService(db_session)
    pair = await service.login(user.username, PASSWORD)
    for _ in range(3):
        pair = await service.refresh(pair.refresh_token)
    assert await get_current_user(pair.access_token, db_session) == user


@pytest.mark.asyncio
async def test_password_change_signs_out_other_devices(db_session) -> None:
    user = await _user(db_session)
    service = AuthService(db_session)
    phone = await service.login(user.username, PASSWORD)
    laptop = await service.login(user.username, PASSWORD)

    fresh = await service.change_password(user, PASSWORD, "new-password-1")

    await _assert_401(service.refresh(phone.refresh_token))
    await _assert_401(get_current_user(laptop.access_token, db_session))
    assert await get_current_user(fresh.access_token, db_session) == user
    await service.refresh(fresh.refresh_token)


@pytest.mark.asyncio
async def test_password_change_needs_the_current_password(db_session) -> None:
    user = await _user(db_session)
    with pytest.raises(HTTPException) as exc:
        await AuthService(db_session).change_password(user, "wrong", "new-password-1")
    assert exc.value.status_code == 400
    assert user.token_version == 0


@pytest.mark.asyncio
async def test_password_reset_signs_out_everywhere(db_session) -> None:
    user = await _user(db_session)
    service = AuthService(db_session)
    pair = await service.login(user.username, PASSWORD)
    raw = await AuthTokenService(db_session).create_token(user.id, AuthTokenPurpose.PASSWORD_RESET)

    await service.confirm_password_reset(raw, "new-password-1")

    await _assert_401(service.refresh(pair.refresh_token))
    await _assert_401(get_current_user(pair.access_token, db_session))


@pytest.mark.asyncio
async def test_logout_all_signs_out_every_device(db_session) -> None:
    user = await _user(db_session)
    service = AuthService(db_session)
    phone = await service.login(user.username, PASSWORD)
    laptop = await service.login(user.username, PASSWORD)

    await service.logout_all(user)

    for pair in (phone, laptop):
        await _assert_401(service.refresh(pair.refresh_token))
        await _assert_401(get_current_user(pair.access_token, db_session))
    left = await db_session.scalars(select(RefreshSession).where(RefreshSession.user_id == user.id))
    assert left.all() == []


@pytest.mark.asyncio
async def test_logout_ends_only_this_device(db_session) -> None:
    user = await _user(db_session)
    service = AuthService(db_session)
    phone = await service.login(user.username, PASSWORD)
    laptop = await service.login(user.username, PASSWORD)

    await service.logout(phone.refresh_token)
    await service.logout("not-a-token")

    await _assert_401(service.refresh(phone.refresh_token))
    await service.refresh(laptop.refresh_token)


@pytest.mark.asyncio
async def test_pre_step_8_tokens_move_to_a_session(db_session) -> None:
    """Tokens issued before the deploy carry no ver/sid: they keep working
    (version 0) until the first version bump."""
    import jwt

    from app.core.config import get_settings

    user = await _user(db_session)
    now = datetime.now(timezone.utc)
    legacy = jwt.encode(
        {"sub": str(user.id), "type": "refresh", "iat": now, "exp": now + timedelta(days=1)},
        get_settings().jwt_secret_key,
        algorithm="HS256",
    )
    service = AuthService(db_session)

    pair = await service.refresh(legacy)
    assert await get_current_user(pair.access_token, db_session) == user

    await service.logout_all(user)
    await _assert_401(service.refresh(legacy))


@pytest.mark.asyncio
async def test_pre_step_8_tokens_stop_at_the_cutoff(db_session, monkeypatch) -> None:
    import jwt

    from app.core.config import get_settings

    user = await _user(db_session)
    now = datetime.now(timezone.utc)
    legacy = jwt.encode(
        {"sub": str(user.id), "type": "refresh", "iat": now, "exp": now + timedelta(days=30)},
        get_settings().jwt_secret_key,
        algorithm="HS256",
    )
    monkeypatch.setattr(auth_service, "LEGACY_REFRESH_CUTOFF", now - timedelta(seconds=1))
    await _assert_401(AuthService(db_session).refresh(legacy))


@pytest.mark.asyncio
async def test_access_token_of_another_version_is_refused(db_session) -> None:
    user = await _user(db_session)
    await _assert_401(get_current_user(create_access_token(str(user.id), version=5), db_session))


def _record_password_changed_emails(monkeypatch, *, fail: bool = False) -> list:
    from app.services.email_service import EmailService

    sent: list = []

    async def _fake(self, user):  # noqa: ANN001 -- mirrors bound method signature
        if fail:
            raise RuntimeError("Resend is down")
        sent.append(user.id)

    monkeypatch.setattr(EmailService, "send_password_changed_email", _fake)
    return sent


@pytest.mark.asyncio
async def test_a_reset_spends_every_other_reset_link(db_session, monkeypatch) -> None:
    """А8 (2026-10-13): two reset emails asked for, the first one used --
    the second link is dead too, and the player is told by email."""
    sent = _record_password_changed_emails(monkeypatch)
    user = await _user(db_session)
    tokens = AuthTokenService(db_session)
    first = await tokens.create_token(user.id, AuthTokenPurpose.PASSWORD_RESET)
    second = await tokens.create_token(user.id, AuthTokenPurpose.PASSWORD_RESET)

    await AuthService(db_session).confirm_password_reset(first, "new-password-1")

    with pytest.raises(HTTPException) as exc:
        await AuthService(db_session).confirm_password_reset(second, "new-password-2")
    assert exc.value.status_code == 410
    assert sent == [user.id]


@pytest.mark.asyncio
async def test_a_password_change_spends_reset_links_and_emails(db_session, monkeypatch) -> None:
    sent = _record_password_changed_emails(monkeypatch)
    user = await _user(db_session)
    pending = await AuthTokenService(db_session).create_token(user.id, AuthTokenPurpose.PASSWORD_RESET)

    await AuthService(db_session).change_password(user, PASSWORD, "new-password-1")

    with pytest.raises(HTTPException) as exc:
        await AuthService(db_session).confirm_password_reset(pending, "new-password-2")
    assert exc.value.status_code == 410
    assert sent == [user.id]


@pytest.mark.asyncio
async def test_a_failed_notification_does_not_fail_the_change(db_session, monkeypatch) -> None:
    _record_password_changed_emails(monkeypatch, fail=True)
    user = await _user(db_session)
    pair = await AuthService(db_session).change_password(user, PASSWORD, "new-password-1")
    assert await get_current_user(pair.access_token, db_session) == user


async def _subscribe(db_session, user: User, endpoint: str) -> None:
    from app.models.push_subscription import PushSubscription

    db_session.add(
        PushSubscription(user_id=user.id, endpoint=endpoint, p256dh_key="p", auth_key="a", user_agent=None)
    )
    await db_session.flush()


async def _endpoints(db_session, user: User) -> set[str]:
    from app.models.push_subscription import PushSubscription

    rows = await db_session.scalars(select(PushSubscription.endpoint).where(PushSubscription.user_id == user.id))
    return set(rows)


@pytest.mark.asyncio
async def test_logout_drops_only_this_devices_push(db_session) -> None:
    """А10 (2026-10-13): a signed-out phone stops getting the player's
    pushes; the laptop still gets them."""
    user = await _user(db_session)
    await _subscribe(db_session, user, "https://push.example/phone")
    await _subscribe(db_session, user, "https://push.example/laptop")
    service = AuthService(db_session)
    phone = await service.login(user.username, PASSWORD)

    await service.logout(phone.refresh_token, "https://push.example/phone")

    assert await _endpoints(db_session, user) == {"https://push.example/laptop"}


@pytest.mark.asyncio
async def test_logout_all_drops_every_push(db_session) -> None:
    user = await _user(db_session)
    await _subscribe(db_session, user, "https://push.example/phone")
    await _subscribe(db_session, user, "https://push.example/laptop")

    await AuthService(db_session).logout_all(user)

    assert await _endpoints(db_session, user) == set()
