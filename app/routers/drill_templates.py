import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.team_event import DrillTemplateCreate, DrillTemplateRead, DrillTemplateRename
from app.services.drill_template_service import DrillTemplateService

router = APIRouter(prefix="/users/me/drill-templates", tags=["team-events"])


@router.get("", response_model=list[DrillTemplateRead])
async def list_templates(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Newest (or most recently renamed) first."""
    return await DrillTemplateService(session).list_templates(current_user)


@router.post("", response_model=DrillTemplateRead)
async def create_template(
    body: DrillTemplateCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """409 once the coach has MAX_TEMPLATES_PER_USER of them."""
    return await DrillTemplateService(session).create_template(current_user, body)


@router.patch("/{template_id}", response_model=DrillTemplateRead)
async def rename_template(
    template_id: uuid.UUID,
    body: DrillTemplateRename,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await DrillTemplateService(session).rename_template(current_user, template_id, body.title)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Drills already copied from it stay as they are."""
    await DrillTemplateService(session).delete_template(current_user, template_id)
