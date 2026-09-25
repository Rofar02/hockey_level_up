import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.team_event import (
    TeamIceScheduleTemplateCreate,
    TeamIceScheduleTemplateRead,
    TeamIceScheduleTemplateUpdate,
)
from app.services.team_event_service import TeamEventService

router = APIRouter(prefix="/teams/{team_id}/ice-schedule-templates", tags=["team-events"])


@router.post("", response_model=TeamIceScheduleTemplateRead)
async def create_template(
    team_id: uuid.UUID,
    body: TeamIceScheduleTemplateCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only. TRAINING only -- games are always one-off (see
    TeamIceScheduleTemplate's own docstring). The background scheduler
    tick stamps future TeamEvent rows from this on its own; nothing gets
    created synchronously here.
    """
    return await TeamEventService(session).create_template(
        current_user, team_id, body.weekday, body.start_time
    )


@router.get("", response_model=list[TeamIceScheduleTemplateRead])
async def list_templates(
    team_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TeamEventService(session).list_templates(current_user, team_id)


@router.patch("/{template_id}", response_model=TeamIceScheduleTemplateRead)
async def set_template_active(
    team_id: uuid.UUID,
    template_id: uuid.UUID,
    body: TeamIceScheduleTemplateUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only. Deactivating never touches TeamEvent rows already
    stamped from this template -- only stops future stamping.
    """
    return await TeamEventService(session).set_template_active(
        current_user, team_id, template_id, body.active
    )


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    team_id: uuid.UUID,
    template_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Captain-only. Already-stamped TeamEvent rows survive (their
    source_template_id just goes to NULL -- ON DELETE SET NULL)."""
    await TeamEventService(session).delete_template(current_user, team_id, template_id)
