import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserCreate


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, user_in: UserCreate, password_hash: str) -> User:
        user = User(
            username=user_in.username,
            email=user_in.email,
            password_hash=password_hash,
            height=user_in.height,
            weight=user_in.weight,
            age=user_in.age,
            position=user_in.position,
            years_of_experience=user_in.years_of_experience,
        )
        self._session.add(user)
        await self._session.flush()
        return user
