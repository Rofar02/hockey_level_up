"""Outbound transactional email via Resend's REST API. First email
integration in the project (see AuthTokenService for the token side of the
verify-email/password-reset flows this exists for) -- no `resend` SDK
dependency added, httpx (already a dependency, see coach_chat_service's
OpenRouter call for the equivalent pattern) is enough for Resend's single
POST /emails endpoint.

Send calls are plain module-level functions (`_send_email`), not methods --
same style as push_service.send_push / coach_chat_service._call_openrouter --
so tests can monkeypatch them and assert on exactly what was sent, with no
real network call and no real Resend key needed.
"""
import logging

import httpx

from app.core.config import get_settings
from app.models.user import User

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"

_VERIFY_EMAIL_TTL_LABEL = "48 часов"
_PASSWORD_RESET_TTL_LABEL = "1 час"


async def _send_email(api_key: str, from_address: str, *, to: str, subject: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"from": from_address, "to": [to], "subject": subject, "text": text},
        )
        response.raise_for_status()


class EmailService:
    """Every send method checks settings.resend_api_key itself and no-ops
    (logging a warning) rather than raising when it's unset -- registration
    and the verify-email resend flow must never fail just because email
    isn't configured yet (see the design discussion). The one place that
    *does* need a hard failure signal, password-reset requests, checks the
    key itself before ever calling in here (AuthService.request_password_reset
    503s upfront) rather than relying on this service to distinguish the two
    cases -- EmailService stays a dumb transport with one uniform rule.
    """

    async def send_verification_email(self, user: User, raw_token: str) -> None:
        settings = get_settings()
        if not settings.resend_api_key:
            logger.warning(
                "RESEND_API_KEY not configured -- skipping verification email for user_id=%s",
                user.id,
            )
            return
        link = f"{settings.frontend_url}/verify-email?token={raw_token}"
        await _send_email(
            settings.resend_api_key,
            settings.email_from_address,
            to=user.email,
            subject="Подтвердите email в IceLevel",
            text=(
                f"Здравствуйте, {user.first_name}!\n\n"
                f"Подтвердите свой email, перейдя по ссылке (действует {_VERIFY_EMAIL_TTL_LABEL}):\n"
                f"{link}\n\n"
                "Если вы не регистрировались в IceLevel, просто проигнорируйте это письмо."
            ),
        )

    async def send_password_reset_email(self, user: User, raw_token: str) -> None:
        settings = get_settings()
        if not settings.resend_api_key:
            logger.warning(
                "RESEND_API_KEY not configured -- skipping password reset email for user_id=%s",
                user.id,
            )
            return
        link = f"{settings.frontend_url}/reset-password?token={raw_token}"
        await _send_email(
            settings.resend_api_key,
            settings.email_from_address,
            to=user.email,
            subject="Восстановление пароля IceLevel",
            text=(
                f"Здравствуйте, {user.first_name}!\n\n"
                f"Чтобы задать новый пароль, перейдите по ссылке (действует {_PASSWORD_RESET_TTL_LABEL}):\n"
                f"{link}\n\n"
                "Если вы не запрашивали восстановление пароля, просто проигнорируйте это письмо -- "
                "текущий пароль останется действующим."
            ),
        )
