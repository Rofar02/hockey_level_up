import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill, UserSkillPreference


class UserSkillPreferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_skill_ids_for_user(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self._session.execute(
            select(UserSkillPreference.skill_id).where(UserSkillPreference.user_id == user_id)
        )
        return list(result.scalars().all())

    async def list_with_skill_names(self, user_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
        result = await self._session.execute(
            select(Skill.id, Skill.name)
            .join(UserSkillPreference, UserSkillPreference.skill_id == Skill.id)
            .where(UserSkillPreference.user_id == user_id)
            .order_by(Skill.name)
        )
        return [(row.id, row.name) for row in result.all()]

    async def replace_for_user(self, user_id: uuid.UUID, skill_ids: list[uuid.UUID]) -> None:
        await self._session.execute(
            delete(UserSkillPreference).where(UserSkillPreference.user_id == user_id)
        )
        for skill_id in skill_ids:
            self._session.add(UserSkillPreference(user_id=user_id, skill_id=skill_id))
        await self._session.flush()
