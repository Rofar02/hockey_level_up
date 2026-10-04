"""Player feedback to the developer (2026-10-04): bug reports, ideas,
anything else -- with an optional screenshot and the device context the
app attaches by itself.

Screenshots are re-encoded (which drops EXIF, GPS included), downscaled and
kept in a private directory -- never under static/ -- since the players are
mostly minors and a screenshot can hold anything; only admins can fetch one.
A new message also emails settings.feedback_notify_email when configured,
best-effort: the player's submission never fails because of email.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.feedback import Feedback, FeedbackKind, FeedbackStatus
from app.models.user import User
from app.services import email_service, image_processing

logger = logging.getLogger(__name__)

TEXT_MIN_CHARS = 5
TEXT_MAX_CHARS = 2000
DAILY_LIMIT = 5
MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024
SCREENSHOT_MAX_SIDE = 1600
CONTEXT_MAX_CHARS = 300
KIND_LABELS = {FeedbackKind.BUG: "Ошибка", FeedbackKind.IDEA: "Идея", FeedbackKind.OTHER: "Другое"}


def _clip(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value[:CONTEXT_MAX_CHARS] or None


class FeedbackService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user: User,
        kind: FeedbackKind,
        text: str,
        *,
        page: str | None = None,
        user_agent: str | None = None,
        screen: str | None = None,
        standalone: bool | None = None,
        app_version: str | None = None,
        screenshot: UploadFile | None = None,
    ) -> Feedback:
        text = text.strip()
        if len(text) < TEXT_MIN_CHARS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Напиши чуть подробнее")
        if len(text) > TEXT_MAX_CHARS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Не больше {TEXT_MAX_CHARS} символов"
            )
        since = datetime.now(timezone.utc) - timedelta(days=1)
        sent_today = await self._session.scalar(
            select(func.count()).select_from(Feedback).where(Feedback.user_id == user.id, Feedback.created_at >= since)
        )
        if (sent_today or 0) >= DAILY_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Сегодня ты уже отправил несколько сообщений — спасибо! Попробуй завтра.",
            )

        screenshot_path = None
        if screenshot is not None:
            screenshot_path = await self._save_screenshot(screenshot)

        feedback = Feedback(
            user_id=user.id,
            kind=kind,
            text=text,
            screenshot_path=screenshot_path,
            context={
                "page": _clip(page),
                "user_agent": _clip(user_agent),
                "screen": _clip(screen),
                "standalone": standalone,
                "app_version": _clip(app_version),
                "level": user.level,
                "premium": user.has_premium,
            },
        )
        self._session.add(feedback)
        await self._session.commit()
        await self._session.refresh(feedback)
        await self._notify(user, feedback)
        return feedback

    async def _save_screenshot(self, file: UploadFile) -> str:
        content = await image_processing.read_limited(file, MAX_SCREENSHOT_BYTES)
        extension = image_processing.detect_image_extension(content)
        image = image_processing.open_oriented(content)
        image.thumbnail((SCREENSHOT_MAX_SIDE, SCREENSHOT_MAX_SIDE), Image.Resampling.LANCZOS)
        # encode() saves without EXIF -- the GPS tag of a phone photo goes too.
        processed = image_processing.encode(image, extension)
        return image_processing.save_new_image_file(Path(get_settings().feedback_upload_dir), processed, extension)

    async def _notify(self, user: User, feedback: Feedback) -> None:
        settings = get_settings()
        if not settings.resend_api_key or not settings.feedback_notify_email:
            return
        context = feedback.context
        try:
            await email_service._send_email(
                settings.resend_api_key,
                settings.email_from_address,
                to=settings.feedback_notify_email,
                subject=f"IceLevel: {KIND_LABELS[feedback.kind]} от {user.first_name or user.email}",
                text=(
                    f"{feedback.text}\n\n"
                    f"Игрок: {user.first_name} {user.last_name} ({user.email}), уровень {user.level}"
                    f"{', премиум' if user.has_premium else ''}\n"
                    f"Страница: {context.get('page')}\n"
                    f"Устройство: {context.get('user_agent')}\n"
                    f"Экран: {context.get('screen')}, с главного экрана: {context.get('standalone')}\n"
                    f"Скриншот: {'есть, в админке' if feedback.screenshot_path else 'нет'}\n"
                    f"{settings.frontend_url}/admin/feedback"
                ),
            )
        except Exception:
            logger.exception("feedback: notification email failed for %s", feedback.id)

    async def list_for_admin(self, status_filter: FeedbackStatus | None, limit: int) -> list[tuple[Feedback, User]]:
        query = select(Feedback, User).join(User, User.id == Feedback.user_id)
        if status_filter is not None:
            query = query.where(Feedback.status == status_filter)
        result = await self._session.execute(query.order_by(Feedback.created_at.desc()).limit(limit))
        return [(row[0], row[1]) for row in result.all()]

    async def set_status(self, feedback_id: uuid.UUID, new_status: FeedbackStatus) -> Feedback:
        feedback = await self._session.get(Feedback, feedback_id)
        if feedback is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
        feedback.status = new_status
        await self._session.commit()
        await self._session.refresh(feedback)
        return feedback

    async def screenshot_file(self, feedback_id: uuid.UUID) -> Path:
        feedback = await self._session.get(Feedback, feedback_id)
        if feedback is None or feedback.screenshot_path is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")
        path = Path(get_settings().feedback_upload_dir) / feedback.screenshot_path
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")
        return path
