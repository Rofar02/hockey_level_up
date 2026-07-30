import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill, SkillMilestone, SkillStatWeight, SkillTag
from app.schemas.skill import (
    SkillCreate,
    SkillMilestoneCreate,
    SkillStatWeightCreate,
    SkillTagCreate,
)


class SkillRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- Skill --

    async def list_skills(self) -> list[Skill]:
        result = await self._session.execute(select(Skill).order_by(Skill.name))
        return list(result.scalars().all())

    async def get_skill(self, skill_id: uuid.UUID) -> Skill | None:
        return await self._session.get(Skill, skill_id)

    async def create_skill(self, data: SkillCreate) -> Skill:
        skill = Skill(**data.model_dump())
        self._session.add(skill)
        await self._session.flush()
        return skill

    async def update_skill(self, skill: Skill, updates: dict) -> Skill:
        for field, value in updates.items():
            setattr(skill, field, value)
        await self._session.flush()
        return skill

    async def delete_skill(self, skill: Skill) -> None:
        await self._session.delete(skill)
        await self._session.flush()

    # -- SkillStatWeight --

    async def list_stat_weights(self, skill_id: uuid.UUID) -> list[SkillStatWeight]:
        result = await self._session.execute(
            select(SkillStatWeight).where(SkillStatWeight.skill_id == skill_id)
        )
        return list(result.scalars().all())

    async def get_stat_weight(self, weight_id: uuid.UUID) -> SkillStatWeight | None:
        return await self._session.get(SkillStatWeight, weight_id)

    async def create_stat_weight(
        self, skill_id: uuid.UUID, data: SkillStatWeightCreate
    ) -> SkillStatWeight:
        weight = SkillStatWeight(skill_id=skill_id, **data.model_dump())
        self._session.add(weight)
        await self._session.flush()
        return weight

    async def update_stat_weight(self, weight: SkillStatWeight, updates: dict) -> SkillStatWeight:
        for field, value in updates.items():
            setattr(weight, field, value)
        await self._session.flush()
        return weight

    async def delete_stat_weight(self, weight: SkillStatWeight) -> None:
        await self._session.delete(weight)
        await self._session.flush()

    # -- SkillTag --

    async def list_tags(self, skill_id: uuid.UUID) -> list[SkillTag]:
        result = await self._session.execute(
            select(SkillTag).where(SkillTag.skill_id == skill_id)
        )
        return list(result.scalars().all())

    async def get_tag(self, tag_id: uuid.UUID) -> SkillTag | None:
        return await self._session.get(SkillTag, tag_id)

    async def create_tag(self, skill_id: uuid.UUID, data: SkillTagCreate) -> SkillTag:
        tag = SkillTag(skill_id=skill_id, **data.model_dump())
        self._session.add(tag)
        await self._session.flush()
        return tag

    async def update_tag(self, tag: SkillTag, updates: dict) -> SkillTag:
        for field, value in updates.items():
            setattr(tag, field, value)
        await self._session.flush()
        return tag

    async def delete_tag(self, tag: SkillTag) -> None:
        await self._session.delete(tag)
        await self._session.flush()

    # -- SkillMilestone --

    async def list_milestones(self, skill_id: uuid.UUID) -> list[SkillMilestone]:
        result = await self._session.execute(
            select(SkillMilestone)
            .where(SkillMilestone.skill_id == skill_id)
            .order_by(SkillMilestone.threshold)
        )
        return list(result.scalars().all())

    async def get_milestone(self, milestone_id: uuid.UUID) -> SkillMilestone | None:
        return await self._session.get(SkillMilestone, milestone_id)

    async def create_milestone(
        self, skill_id: uuid.UUID, data: SkillMilestoneCreate
    ) -> SkillMilestone:
        milestone = SkillMilestone(skill_id=skill_id, **data.model_dump())
        self._session.add(milestone)
        await self._session.flush()
        return milestone

    async def update_milestone(self, milestone: SkillMilestone, updates: dict) -> SkillMilestone:
        for field, value in updates.items():
            setattr(milestone, field, value)
        await self._session.flush()
        return milestone

    async def delete_milestone(self, milestone: SkillMilestone) -> None:
        await self._session.delete(milestone)
        await self._session.flush()
