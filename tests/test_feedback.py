"""Player feedback (2026-10-04): bug/idea/other with optional screenshot and
device context; daily limit; screenshots private (admin-only) with EXIF
stripped; best-effort email to the developer."""
import io
import uuid

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from app.core.config import Settings
from app.models.feedback import FeedbackKind, FeedbackStatus
from app.models.user import User
from app.services import feedback_service
from app.services.feedback_service import DAILY_LIMIT, FeedbackService


def _user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"feedback_{unique}",
        email=f"feedback_{unique}@example.com",
        password_hash="irrelevant",
        first_name="Артём",
        last_name="Иванов",
    )


def _settings(tmp_path, **extra) -> Settings:
    return Settings(feedback_upload_dir=str(tmp_path), **extra)


def _jpeg_with_gps() -> bytes:
    image = Image.new("RGB", (3000, 2000), "white")
    exif = Image.Exif()
    exif[0x8825] = {2: (55.0, 45.0, 0.0)}  # GPSInfo
    output = io.BytesIO()
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


@pytest.mark.asyncio
async def test_feedback_is_saved_with_context(db_session, monkeypatch, tmp_path) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()
    monkeypatch.setattr(feedback_service, "get_settings", lambda: _settings(tmp_path))

    feedback = await FeedbackService(db_session).create(
        user, FeedbackKind.BUG, "Капсула уехала в середину", page="/coach", standalone=True, screen="390x844"
    )

    assert feedback.status == FeedbackStatus.NEW
    assert feedback.context["page"] == "/coach"
    assert feedback.context["standalone"] is True
    assert feedback.screenshot_path is None


@pytest.mark.asyncio
async def test_too_short_text_is_rejected(db_session, monkeypatch, tmp_path) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()
    monkeypatch.setattr(feedback_service, "get_settings", lambda: _settings(tmp_path))

    with pytest.raises(HTTPException) as exc_info:
        await FeedbackService(db_session).create(user, FeedbackKind.IDEA, "  ок ")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_daily_limit(db_session, monkeypatch, tmp_path) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()
    monkeypatch.setattr(feedback_service, "get_settings", lambda: _settings(tmp_path))
    service = FeedbackService(db_session)

    for i in range(DAILY_LIMIT):
        await service.create(user, FeedbackKind.OTHER, f"Сообщение номер {i}")
    with pytest.raises(HTTPException) as exc_info:
        await service.create(user, FeedbackKind.OTHER, "Ещё одно сообщение")
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_screenshot_is_private_downscaled_and_loses_exif(db_session, monkeypatch, tmp_path) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()
    monkeypatch.setattr(feedback_service, "get_settings", lambda: _settings(tmp_path))
    upload = UploadFile(file=io.BytesIO(_jpeg_with_gps()), filename="photo.jpg")

    feedback = await FeedbackService(db_session).create(user, FeedbackKind.BUG, "Вот скриншот бага", screenshot=upload)

    path = await FeedbackService(db_session).screenshot_file(feedback.id)
    assert path.parent == tmp_path
    saved = Image.open(path)
    assert max(saved.size) <= feedback_service.SCREENSHOT_MAX_SIDE
    assert 0x8825 not in saved.getexif()


@pytest.mark.asyncio
async def test_email_goes_to_the_developer_and_never_breaks_submission(db_session, monkeypatch, tmp_path) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()
    sent: list[dict] = []

    async def _fake_send(api_key, from_address, *, to, subject, text):
        sent.append({"to": to, "subject": subject, "text": text})
        raise RuntimeError("smtp down")

    monkeypatch.setattr(feedback_service.email_service, "_send_email", _fake_send)
    monkeypatch.setattr(
        feedback_service,
        "get_settings",
        lambda: _settings(tmp_path, resend_api_key="key", feedback_notify_email="dev@example.com"),
    )

    feedback = await FeedbackService(db_session).create(user, FeedbackKind.IDEA, "Добавьте тёмную тему")

    assert feedback.id is not None  # saved even though the email failed
    assert sent[0]["to"] == "dev@example.com"
    assert "Добавьте тёмную тему" in sent[0]["text"]


@pytest.mark.asyncio
async def test_admin_list_and_status(db_session, monkeypatch, tmp_path) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()
    monkeypatch.setattr(feedback_service, "get_settings", lambda: _settings(tmp_path))
    service = FeedbackService(db_session)
    feedback = await service.create(user, FeedbackKind.BUG, "Не грузится план")

    await service.set_status(feedback.id, FeedbackStatus.DONE)

    rows = await service.list_for_admin(FeedbackStatus.DONE, 500)
    assert any(item.id == feedback.id and owner.id == user.id for item, owner in rows)


@pytest.mark.asyncio
async def test_every_admin_device_gets_a_push_opening_the_inbox(db_session, monkeypatch, tmp_path) -> None:
    from app.models.push_subscription import PushSubscription

    player, admin, other_admin, regular = _user(), _user(), _user(), _user()
    admin.is_admin = True
    other_admin.is_admin = True
    db_session.add_all([player, admin, other_admin, regular])
    await db_session.flush()
    for owner in (admin, other_admin, regular):
        db_session.add(
            PushSubscription(user_id=owner.id, endpoint=f"https://push.example/{owner.id}", p256dh_key="k", auth_key="a")
        )
    await db_session.flush()
    pushed: list[dict] = []

    async def _fake_push(session, subscription, title, body, url=None):
        pushed.append({"endpoint": subscription.endpoint, "title": title, "body": body, "url": url})
        return True

    monkeypatch.setattr(feedback_service.push_service, "send_push", _fake_push)
    monkeypatch.setattr(feedback_service, "get_settings", lambda: _settings(tmp_path))

    await FeedbackService(db_session).create(player, FeedbackKind.BUG, "Пропало нижнее меню после сворачивания")

    endpoints = {item["endpoint"] for item in pushed}
    assert endpoints == {f"https://push.example/{admin.id}", f"https://push.example/{other_admin.id}"}
    assert all(item["url"] == "/admin/feedback" for item in pushed)
    assert pushed[0]["title"] == "Обратная связь: Ошибка"
    assert "Пропало нижнее меню" in pushed[0]["body"]


@pytest.mark.asyncio
async def test_a_failing_push_never_breaks_the_submission(db_session, monkeypatch, tmp_path) -> None:
    from app.models.push_subscription import PushSubscription

    player, admin = _user(), _user()
    admin.is_admin = True
    db_session.add_all([player, admin])
    await db_session.flush()
    db_session.add(PushSubscription(user_id=admin.id, endpoint="https://push.example/x", p256dh_key="k", auth_key="a"))
    await db_session.flush()

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("push service down")

    monkeypatch.setattr(feedback_service.push_service, "send_push", _boom)
    monkeypatch.setattr(feedback_service, "get_settings", lambda: _settings(tmp_path))

    feedback = await FeedbackService(db_session).create(player, FeedbackKind.IDEA, "Добавьте тёмную тему")

    assert feedback.id is not None
