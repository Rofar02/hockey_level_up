from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import EquipmentType
from app.models.user import User


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def update_equipment_access(self, user: User, equipment_access: EquipmentType) -> User:
        user.equipment_access = equipment_access
        await self._session.commit()
        await self._session.refresh(user)
        return user
