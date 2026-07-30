import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user, require_admin
from app.schemas.skill import (
    SkillCreate,
    SkillDetailRead,
    SkillMilestoneCreate,
    SkillMilestoneRead,
    SkillMilestoneUpdate,
    SkillRead,
    SkillStatWeightCreate,
    SkillStatWeightRead,
    SkillStatWeightUpdate,
    SkillSummaryRead,
    SkillTagCreate,
    SkillTagRead,
    SkillTagUpdate,
    SkillUpdate,
)
from app.services.skill_service import SkillService

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[SkillSummaryRead])
async def list_skills(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SkillService(session).list_skills_for_user(current_user.id)


@router.get("/{skill_id}", response_model=SkillDetailRead)
async def get_skill(
    skill_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SkillService(session).get_skill_detail(skill_id, current_user.id)


@router.post("", response_model=SkillRead, status_code=status.HTTP_201_CREATED)
async def create_skill(
    body: SkillCreate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SkillService(session).create_skill(body)


@router.patch("/{skill_id}", response_model=SkillRead)
async def update_skill(
    skill_id: uuid.UUID,
    body: SkillUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SkillService(session).update_skill(skill_id, body)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await SkillService(session).delete_skill(skill_id)


@router.post(
    "/{skill_id}/stat-weights",
    response_model=SkillStatWeightRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_stat_weight(
    skill_id: uuid.UUID,
    body: SkillStatWeightCreate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SkillService(session).create_stat_weight(skill_id, body)


@router.patch("/{skill_id}/stat-weights/{weight_id}", response_model=SkillStatWeightRead)
async def update_stat_weight(
    skill_id: uuid.UUID,
    weight_id: uuid.UUID,
    body: SkillStatWeightUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SkillService(session).update_stat_weight(skill_id, weight_id, body)


@router.delete("/{skill_id}/stat-weights/{weight_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stat_weight(
    skill_id: uuid.UUID,
    weight_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await SkillService(session).delete_stat_weight(skill_id, weight_id)


@router.post("/{skill_id}/tags", response_model=SkillTagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(
    skill_id: uuid.UUID,
    body: SkillTagCreate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SkillService(session).create_tag(skill_id, body)


@router.patch("/{skill_id}/tags/{tag_id}", response_model=SkillTagRead)
async def update_tag(
    skill_id: uuid.UUID,
    tag_id: uuid.UUID,
    body: SkillTagUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SkillService(session).update_tag(skill_id, tag_id, body)


@router.delete("/{skill_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    skill_id: uuid.UUID,
    tag_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await SkillService(session).delete_tag(skill_id, tag_id)


@router.post(
    "/{skill_id}/milestones", response_model=SkillMilestoneRead, status_code=status.HTTP_201_CREATED
)
async def create_milestone(
    skill_id: uuid.UUID,
    body: SkillMilestoneCreate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SkillService(session).create_milestone(skill_id, body)


@router.patch("/{skill_id}/milestones/{milestone_id}", response_model=SkillMilestoneRead)
async def update_milestone(
    skill_id: uuid.UUID,
    milestone_id: uuid.UUID,
    body: SkillMilestoneUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SkillService(session).update_milestone(skill_id, milestone_id, body)


@router.delete("/{skill_id}/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_milestone(
    skill_id: uuid.UUID,
    milestone_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await SkillService(session).delete_milestone(skill_id, milestone_id)
