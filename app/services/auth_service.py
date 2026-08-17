import logging
import re
import secrets
import uuid

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.auth_token import AuthTokenPurpose
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenPair
from app.schemas.user import UserCreate
from app.services.auth_token_service import AuthTokenService
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

# Registration no longer collects a username from the client, but the
# column is still unique/non-null (existing accounts still log in with
# theirs) -- generated from the email's local part for a vaguely readable
# value, with a random suffix so collisions between two emails sharing a
# local part (or a retry) are essentially impossible.
_USERNAME_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9]")
_USERNAME_GENERATION_ATTEMPTS = 10

# Same generation pattern as TeamService._generate_invite_code (also
# secrets.token_hex(4).upper(), also a bounded-retry uniqueness loop) --
# one friend_code per user rather than one invite_code per team.
_FRIEND_CODE_GENERATION_ATTEMPTS = 10


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._tokens = AuthTokenService(session)
        self._email = EmailService()

    async def register(self, user_in: UserCreate) -> User:
        if not user_in.privacy_consent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Privacy policy consent is required",
            )
        if await self._users.get_by_email(user_in.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
            )

        username = await self._generate_username(user_in.email)
        friend_code = await self._generate_friend_code()
        user = await self._users.create(user_in, hash_password(user_in.password), username, friend_code)
        await self._session.commit()

        # Best-effort: a failure here (no RESEND_API_KEY in dev, Resend
        # down, whatever) must never undo an already-committed account --
        # the user just ends up unverified and can hit /verify-email/resend
        # later. Logged so a real production outage is still visible
        # somewhere, just not to the registering user as a 500.
        #
        # A SAVEPOINT (begin_nested), not session.rollback(): a plain
        # rollback() would roll back the *whole* session and expire every
        # object it's tracking -- including `user`, already safely
        # committed above -- forcing a reload on the caller's next attribute
        # access, which fails outside an awaited context. The nested
        # transaction confines the rollback to just the token/email attempt.
        try:
            async with self._session.begin_nested():
                raw_token = await self._tokens.create_token(user.id, AuthTokenPurpose.EMAIL_VERIFY)
                await self._email.send_verification_email(user, raw_token)
            await self._session.commit()
        except Exception:
            logger.exception(
                "Failed to send verification email for newly-registered user_id=%s", user.id
            )

        return user

    async def resend_verification_email(self, user: User) -> None:
        if user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Email уже подтверждён"
            )
        raw_token = await self._tokens.create_token(user.id, AuthTokenPurpose.EMAIL_VERIFY)
        # Unlike register()'s best-effort send (a failure there must never
        # undo an already-created account) and request_password_reset's
        # (which must stay silent either way to avoid leaking account
        # existence), this is the one send the caller is directly waiting
        # on and already knows their own email address for -- so a real
        # delivery failure (Resend down, domain not verified, etc.) should
        # surface as a clear error instead of an opaque 500.
        try:
            await self._email.send_verification_email(user, raw_token)
        except Exception:
            logger.exception("Failed to resend verification email for user_id=%s", user.id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Не удалось отправить письмо. Попробуйте позже.",
            ) from None
        await self._session.commit()

    async def confirm_email_verification(self, raw_token: str) -> User:
        user = await self._tokens.consume_token(raw_token, AuthTokenPurpose.EMAIL_VERIFY)
        user.email_verified = True
        await self._session.commit()
        return user

    async def request_password_reset(self, email: str) -> None:
        settings = get_settings()
        if not settings.resend_api_key:
            # Checked *before* looking the user up, and unconditionally --
            # this can never leak whether `email` is registered, unlike a
            # check made only on the "user exists" branch would.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Восстановление пароля временно недоступно",
            )

        user = await self._users.get_by_email(email)
        if user is None:
            # Same generic outcome as the success path below -- the caller
            # (router) returns the identical response either way, so
            # nothing here may distinguish "no such account" by timing,
            # status code, or body.
            return

        # Same SAVEPOINT reasoning as register()'s verification-email attempt
        # above -- a failure here must not expire `user`-tracking state for
        # anything else still using this session, and the router returns the
        # same generic response regardless of what happens in here anyway.
        try:
            async with self._session.begin_nested():
                raw_token = await self._tokens.create_token(user.id, AuthTokenPurpose.PASSWORD_RESET)
                await self._email.send_password_reset_email(user, raw_token)
            await self._session.commit()
        except Exception:
            logger.exception("Failed to send password reset email for user_id=%s", user.id)

    async def confirm_password_reset(self, raw_token: str, new_password: str) -> None:
        user = await self._tokens.consume_token(raw_token, AuthTokenPurpose.PASSWORD_RESET)
        user.password_hash = hash_password(new_password)
        await self._session.commit()

    async def _generate_username(self, email: str) -> str:
        local_part = email.split("@", 1)[0]
        base = _USERNAME_SANITIZE_RE.sub("", local_part).lower()[:30] or "user"
        for _ in range(_USERNAME_GENERATION_ATTEMPTS):
            candidate = f"{base}_{secrets.token_hex(4)}"
            if await self._users.get_by_username(candidate) is None:
                return candidate
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate a unique username",
        )

    async def _generate_friend_code(self) -> str:
        for _ in range(_FRIEND_CODE_GENERATION_ATTEMPTS):
            candidate = secrets.token_hex(4).upper()
            if await self._users.get_by_friend_code(candidate) is None:
                return candidate
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate a unique friend code",
        )

    async def authenticate(self, identifier: str, password: str) -> User:
        # New accounts have no client-chosen username, so they log in by
        # email -- but existing accounts (created back when registration
        # did collect one) still expect to log in with it, so both are
        # accepted here rather than switching the login form's meaning
        # out from under them.
        user = await self._users.get_by_username(identifier)
        if user is None:
            user = await self._users.get_by_email(identifier)
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username/email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    async def login(self, identifier: str, password: str) -> TokenPair:
        user = await self.authenticate(identifier, password)
        return self._issue_tokens(user.id)

    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            subject = decode_token(refresh_token, TokenType.REFRESH)
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            ) from exc

        user = await self._users.get_by_id(uuid.UUID(subject))
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        return self._issue_tokens(user.id)

    @staticmethod
    def _issue_tokens(user_id: uuid.UUID) -> TokenPair:
        subject = str(user_id)
        return TokenPair(
            access_token=create_access_token(subject),
            refresh_token=create_refresh_token(subject),
        )
