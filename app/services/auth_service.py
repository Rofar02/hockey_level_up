import re
import secrets
import uuid

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenPair
from app.schemas.user import UserCreate

# Registration no longer collects a username from the client, but the
# column is still unique/non-null (existing accounts still log in with
# theirs) -- generated from the email's local part for a vaguely readable
# value, with a random suffix so collisions between two emails sharing a
# local part (or a retry) are essentially impossible.
_USERNAME_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9]")
_USERNAME_GENERATION_ATTEMPTS = 10


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

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
        user = await self._users.create(user_in, hash_password(user_in.password), username)
        await self._session.commit()
        return user

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
