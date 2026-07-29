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


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    async def register(self, user_in: UserCreate) -> User:
        if await self._users.get_by_username(user_in.username):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Username already taken"
            )
        if await self._users.get_by_email(user_in.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
            )

        user = await self._users.create(user_in, hash_password(user_in.password))
        await self._session.commit()
        return user

    async def authenticate(self, username: str, password: str) -> User:
        user = await self._users.get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    async def login(self, username: str, password: str) -> TokenPair:
        user = await self.authenticate(username, password)
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
