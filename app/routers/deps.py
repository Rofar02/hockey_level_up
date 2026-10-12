import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenType, decode_claims, token_version
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = decode_claims(token, TokenType.ACCESS)
        user_id = uuid.UUID(claims["sub"])
    except (InvalidTokenError, ValueError) as exc:
        raise credentials_error from exc

    user = await UserRepository(session).get_by_id(user_id)
    # A password change or "Выйти на всех устройствах" bumped the version:
    # every token issued before it is dead, not just the refresh ones.
    if user is None or token_version(claims) != user.token_version:
        raise credentials_error
    return user


async def require_admin(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return current_user


async def require_premium(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if not current_user.has_premium:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Эта функция доступна с премиум-подпиской"
        )
    return current_user
