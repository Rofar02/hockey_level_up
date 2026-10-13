import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jwt import InvalidTokenError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_claims,
    hash_password_async,
    token_version,
    verify_password_async,
)
from app.models.auth_token import AuthTokenPurpose
from app.models.push_subscription import PushSubscription
from app.models.refresh_session import RefreshSession
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

# How long the refresh token just swapped out still works (step 8, security,
# 2): two tabs refreshing at once, or a retry after the answer got lost on a
# bad network, send the same token twice. Past it, a used token ends the
# device's session -- someone else has it.
REFRESH_REUSE_GRACE = timedelta(seconds=30)
# 2026-10-13 (А7): refresh tokens from before step 8 (deployed 2026-10-12)
# carry no device session, so a copy of one could mint new sessions over and
# over. They expire on their own within refresh_token_expire_days (30) of
# being issued; past this date none can be genuine, whatever exp says.
LEGACY_REFRESH_CUTOFF = datetime(2026, 11, 12, tzinfo=timezone.utc)


def _new_jti() -> str:
    return uuid.uuid4().hex


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._tokens = AuthTokenService(session)
        self._email = EmailService()

    async def is_email_available(self, email: str) -> bool:
        """Public, pre-account check (2026-08-29: registration step 1 should
        say the email is taken before the athlete fills in the rest of the
        wizard, not just fail at the final submit). Unlike
        request_password_reset, this one's whole point IS to reveal whether
        an email is registered -- that's an accepted, deliberate trade-off
        for a signup flow, not an oversight of the same anti-enumeration
        concern password-reset guards against."""
        return await self._users.get_by_email(email) is None

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
        user = await self._users.create(user_in, await hash_password_async(user_in.password), username, friend_code)
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
        user.password_hash = await hash_password_async(new_password)
        # Whoever knew the old password is signed out everywhere, and no
        # other reset link sent earlier still works (А8).
        await self._end_all_sessions(user)
        await self._tokens.spend_unused(user.id, AuthTokenPurpose.PASSWORD_RESET)
        await self._session.commit()
        await self._notify_password_changed(user)

    async def _notify_password_changed(self, user: User) -> None:
        # After the commit and best-effort: the password is changed either
        # way, a Resend outage must not turn that into an error.
        try:
            await self._email.send_password_changed_email(user)
        except Exception:
            logger.exception("Failed to send password changed email for user_id=%s", user.id)

    async def change_password(self, user: User, current_password: str, new_password: str) -> TokenPair:
        """Signs out every other device; this one gets a fresh pair."""
        if not await verify_password_async(current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный текущий пароль")
        user.password_hash = await hash_password_async(new_password)
        await self._end_all_sessions(user)
        await self._tokens.spend_unused(user.id, AuthTokenPurpose.PASSWORD_RESET)
        pair = await self._start_session(user)
        await self._notify_password_changed(user)
        return pair

    async def logout(self, refresh_token: str, push_endpoint: str | None = None) -> None:
        """Ends this device's session and its push subscription (А10). Quiet
        on a bad or expired token -- the client forgets its tokens either
        way."""
        try:
            claims = decode_claims(refresh_token, TokenType.REFRESH)
            session_id = uuid.UUID(str(claims.get("sid")))
            user_id = uuid.UUID(claims["sub"])
        except (InvalidTokenError, ValueError):
            return
        await self._session.execute(
            delete(RefreshSession).where(RefreshSession.id == session_id, RefreshSession.user_id == user_id)
        )
        if push_endpoint:
            await self._session.execute(
                delete(PushSubscription).where(
                    PushSubscription.user_id == user_id, PushSubscription.endpoint == push_endpoint
                )
            )
        await self._session.commit()

    async def logout_all(self, user: User) -> None:
        """«Выйти на всех устройствах»: every token issued so far, access
        ones included, stops working -- and no device keeps getting the
        player's pushes (А10)."""
        await self._end_all_sessions(user)
        await self._session.execute(delete(PushSubscription).where(PushSubscription.user_id == user.id))
        await self._session.commit()

    async def _end_all_sessions(self, user: User) -> None:
        user.token_version += 1
        await self._session.execute(delete(RefreshSession).where(RefreshSession.user_id == user.id))

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
        if user is None or not await verify_password_async(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username/email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    async def login(self, identifier: str, password: str) -> TokenPair:
        user = await self.authenticate(identifier, password)
        return await self._start_session(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        try:
            claims = decode_claims(refresh_token, TokenType.REFRESH)
            user_id = uuid.UUID(claims["sub"])
        except (InvalidTokenError, ValueError) as exc:
            raise invalid from exc

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        if token_version(claims) != user.token_version:
            raise invalid

        if "sid" not in claims:
            # Issued before step 8 -- moves to a device session once; the
            # next version bump ends it like any other.
            if datetime.now(timezone.utc) >= LEGACY_REFRESH_CUTOFF:
                raise invalid
            return await self._start_session(user)
        try:
            session_id = uuid.UUID(str(claims["sid"]))
        except ValueError as exc:
            raise invalid from exc

        # Locked: two refreshes of one device run one after another, so the
        # second sees the first one's rotation and takes the grace path.
        device = await self._session.scalar(
            select(RefreshSession)
            .where(RefreshSession.id == session_id, RefreshSession.user_id == user.id)
            .with_for_update()
        )
        now = datetime.now(timezone.utc)
        if device is None or device.expires_at <= now:
            raise invalid
        jti = claims.get("jti")
        if jti == device.current_jti:
            device.previous_jti = device.current_jti
            device.current_jti = _new_jti()
            device.rotated_at = now
            device.expires_at = now + self._refresh_lifetime()
        elif not (
            jti is not None
            and jti == device.previous_jti
            and device.rotated_at is not None
            and now - device.rotated_at <= REFRESH_REUSE_GRACE
        ):
            # A refresh token used twice: whoever holds the other copy
            # loses this device's session along with the player.
            logger.warning("Refresh token reuse, session %s ended (user_id=%s)", device.id, user.id)
            await self._session.delete(device)
            await self._session.commit()
            raise invalid
        pair = self._issue_tokens(user, device)
        await self._session.commit()
        return pair

    async def _start_session(self, user: User) -> TokenPair:
        now = datetime.now(timezone.utc)
        # The player's own long-expired devices go on the way.
        await self._session.execute(
            delete(RefreshSession).where(RefreshSession.user_id == user.id, RefreshSession.expires_at <= now)
        )
        device = RefreshSession(
            id=uuid.uuid4(), user_id=user.id, current_jti=_new_jti(), expires_at=now + self._refresh_lifetime()
        )
        self._session.add(device)
        pair = self._issue_tokens(user, device)
        await self._session.commit()
        return pair

    @staticmethod
    def _refresh_lifetime() -> timedelta:
        return timedelta(days=get_settings().refresh_token_expire_days)

    @staticmethod
    def _issue_tokens(user: User, device: RefreshSession) -> TokenPair:
        subject = str(user.id)
        return TokenPair(
            access_token=create_access_token(subject, user.token_version),
            refresh_token=create_refresh_token(subject, user.token_version, str(device.id), device.current_jti),
        )
