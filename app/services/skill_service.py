import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill, SkillMilestone, SkillStatWeight, SkillTag
from app.repositories.exercise_repository import ExerciseRepository
from app.repositories.progress_repository import ProgressRepository
from app.repositories.skill_repository import SkillRepository
from app.schemas.skill import (
    NextMilestoneRead,
    SkillCreate,
    SkillDetailRead,
    SkillMilestoneCreate,
    SkillMilestoneStatusRead,
    SkillMilestoneUpdate,
    SkillStatWeightCreate,
    SkillStatWeightUpdate,
    SkillSummaryRead,
    SkillTagCreate,
    SkillTagUpdate,
    SkillUpdate,
    StatContributionRead,
)
from app.services.stat_service import get_effective_value

WEIGHT_SUM_EPSILON = 1e-6


class SkillService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._skills = SkillRepository(session)
        self._progress = ProgressRepository(session)
        self._exercises = ExerciseRepository(session)

    # -- pure computed value (no writes) --

    async def get_skill_value(self, skill_id: uuid.UUID, user_id: uuid.UUID) -> float:
        breakdown = await self._compute_breakdown(skill_id, user_id)
        return sum(item.contribution for item in breakdown)

    async def _compute_breakdown(
        self, skill_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[StatContributionRead]:
        weights = await self._skills.list_stat_weights(skill_id)
        now = datetime.now(timezone.utc)

        breakdown = []
        for weight in weights:
            stat = await self._progress.get_user_stat(user_id, weight.stat_type)
            effective_value = get_effective_value(stat, now) if stat is not None else 0.0
            breakdown.append(
                StatContributionRead(
                    stat_type=weight.stat_type,
                    weight=weight.weight,
                    effective_value=effective_value,
                    contribution=effective_value * weight.weight,
                )
            )
        return breakdown

    # -- read endpoints --

    async def list_skills_for_user(self, user_id: uuid.UUID) -> list[SkillSummaryRead]:
        skills = await self._skills.list_skills()
        results = []
        for skill in skills:
            value = await self.get_skill_value(skill.id, user_id)
            milestones = await self._skills.list_milestones(skill.id)
            next_milestone = next((m for m in milestones if m.threshold > value), None)
            results.append(
                SkillSummaryRead(
                    id=skill.id,
                    name=skill.name,
                    value=value,
                    next_milestone=(
                        NextMilestoneRead(
                            title=next_milestone.title,
                            threshold=next_milestone.threshold,
                            points_remaining=next_milestone.threshold - value,
                        )
                        if next_milestone is not None
                        else None
                    ),
                )
            )
        return results

    async def get_skill_detail(self, skill_id: uuid.UUID, user_id: uuid.UUID) -> SkillDetailRead:
        skill = await self._get_skill_or_404(skill_id)
        breakdown = await self._compute_breakdown(skill_id, user_id)
        value = sum(item.contribution for item in breakdown)

        milestones = await self._skills.list_milestones(skill_id)
        milestone_reads = [
            SkillMilestoneStatusRead(
                id=m.id,
                threshold=m.threshold,
                title=m.title,
                description=m.description,
                achieved=value >= m.threshold,
            )
            for m in milestones
        ]

        return SkillDetailRead(
            id=skill.id,
            name=skill.name,
            value=value,
            stat_breakdown=breakdown,
            milestones=milestone_reads,
        )

    # -- Skill admin CRUD --

    async def create_skill(self, data: SkillCreate) -> Skill:
        try:
            skill = await self._skills.create_skill(data)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Skill name already exists"
            ) from exc
        return skill

    async def update_skill(self, skill_id: uuid.UUID, data: SkillUpdate) -> Skill:
        skill = await self._get_skill_or_404(skill_id)
        updates = data.model_dump(exclude_unset=True)
        try:
            await self._skills.update_skill(skill, updates)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Skill name already exists"
            ) from exc
        await self._session.refresh(skill)
        return skill

    async def delete_skill(self, skill_id: uuid.UUID) -> None:
        skill = await self._get_skill_or_404(skill_id)
        await self._skills.delete_skill(skill)
        await self._session.commit()

    # -- SkillStatWeight admin CRUD --

    async def create_stat_weight(
        self, skill_id: uuid.UUID, data: SkillStatWeightCreate
    ) -> SkillStatWeight:
        await self._get_skill_or_404(skill_id)
        await self._validate_weight_sum(skill_id, data.weight)
        try:
            weight = await self._skills.create_stat_weight(skill_id, data)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A weight for this stat already exists on this skill",
            ) from exc
        return weight

    async def update_stat_weight(
        self, skill_id: uuid.UUID, weight_id: uuid.UUID, data: SkillStatWeightUpdate
    ) -> SkillStatWeight:
        weight = await self._get_stat_weight_or_404(skill_id, weight_id)
        updates = data.model_dump(exclude_unset=True)
        new_weight_value = updates.get("weight", weight.weight)
        await self._validate_weight_sum(skill_id, new_weight_value, exclude_weight_id=weight_id)
        try:
            await self._skills.update_stat_weight(weight, updates)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A weight for this stat already exists on this skill",
            ) from exc
        await self._session.refresh(weight)
        return weight

    async def _validate_weight_sum(
        self,
        skill_id: uuid.UUID,
        new_weight: float,
        *,
        exclude_weight_id: uuid.UUID | None = None,
    ) -> None:
        existing = await self._skills.list_stat_weights(skill_id)
        total = new_weight + sum(
            w.weight for w in existing if exclude_weight_id is None or w.id != exclude_weight_id
        )
        if total > 1.0 + WEIGHT_SUM_EPSILON:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"sum of weights for this skill would exceed 1.0: got {round(total, 6)}",
            )

    async def delete_stat_weight(self, skill_id: uuid.UUID, weight_id: uuid.UUID) -> None:
        weight = await self._get_stat_weight_or_404(skill_id, weight_id)
        await self._skills.delete_stat_weight(weight)
        await self._session.commit()

    # -- SkillTag admin CRUD --

    async def create_tag(self, skill_id: uuid.UUID, data: SkillTagCreate) -> SkillTag:
        await self._get_skill_or_404(skill_id)
        exercise = await self._exercises.get_by_id(data.exercise_id)
        if exercise is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found")
        try:
            tag = await self._skills.create_tag(skill_id, data)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This exercise is already tagged with this skill",
            ) from exc
        return tag

    async def update_tag(
        self, skill_id: uuid.UUID, tag_id: uuid.UUID, data: SkillTagUpdate
    ) -> SkillTag:
        tag = await self._get_tag_or_404(skill_id, tag_id)
        updates = data.model_dump(exclude_unset=True)
        await self._skills.update_tag(tag, updates)
        await self._session.commit()
        await self._session.refresh(tag)
        return tag

    async def delete_tag(self, skill_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        tag = await self._get_tag_or_404(skill_id, tag_id)
        await self._skills.delete_tag(tag)
        await self._session.commit()

    # -- SkillMilestone admin CRUD --

    async def create_milestone(
        self, skill_id: uuid.UUID, data: SkillMilestoneCreate
    ) -> SkillMilestone:
        await self._get_skill_or_404(skill_id)
        milestone = await self._skills.create_milestone(skill_id, data)
        await self._session.commit()
        return milestone

    async def update_milestone(
        self, skill_id: uuid.UUID, milestone_id: uuid.UUID, data: SkillMilestoneUpdate
    ) -> SkillMilestone:
        milestone = await self._get_milestone_or_404(skill_id, milestone_id)
        updates = data.model_dump(exclude_unset=True)
        await self._skills.update_milestone(milestone, updates)
        await self._session.commit()
        await self._session.refresh(milestone)
        return milestone

    async def delete_milestone(self, skill_id: uuid.UUID, milestone_id: uuid.UUID) -> None:
        milestone = await self._get_milestone_or_404(skill_id, milestone_id)
        await self._skills.delete_milestone(milestone)
        await self._session.commit()

    # -- lookups shared by the admin endpoints --

    async def _get_skill_or_404(self, skill_id: uuid.UUID) -> Skill:
        skill = await self._skills.get_skill(skill_id)
        if skill is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
        return skill

    async def _get_stat_weight_or_404(
        self, skill_id: uuid.UUID, weight_id: uuid.UUID
    ) -> SkillStatWeight:
        weight = await self._skills.get_stat_weight(weight_id)
        if weight is None or weight.skill_id != skill_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Skill stat weight not found"
            )
        return weight

    async def _get_tag_or_404(self, skill_id: uuid.UUID, tag_id: uuid.UUID) -> SkillTag:
        tag = await self._skills.get_tag(tag_id)
        if tag is None or tag.skill_id != skill_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill tag not found")
        return tag

    async def _get_milestone_or_404(
        self, skill_id: uuid.UUID, milestone_id: uuid.UUID
    ) -> SkillMilestone:
        milestone = await self._skills.get_milestone(milestone_id)
        if milestone is None or milestone.skill_id != skill_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Skill milestone not found"
            )
        return milestone
