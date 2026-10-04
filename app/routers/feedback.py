import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.feedback import FeedbackKind, FeedbackStatus
from app.models.user import User
from app.routers.deps import get_current_user, require_admin
from app.schemas.feedback import (
    FeedbackAdminRead,
    FeedbackCreatedRead,
    FeedbackStatusUpdate,
)
from app.services.feedback_service import FeedbackService

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackCreatedRead, status_code=status.HTTP_201_CREATED)
async def send_feedback(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    kind: Annotated[FeedbackKind, Form()],
    text: Annotated[str, Form()],
    page: Annotated[str | None, Form()] = None,
    user_agent: Annotated[str | None, Form()] = None,
    screen: Annotated[str | None, Form()] = None,
    standalone: Annotated[bool | None, Form()] = None,
    app_version: Annotated[str | None, Form()] = None,
    screenshot: Annotated[UploadFile | None, File()] = None,
):
    """A player's bug report / idea / message (FeedbackService)."""
    feedback = await FeedbackService(session).create(
        current_user,
        kind,
        text,
        page=page,
        user_agent=user_agent,
        screen=screen,
        standalone=standalone,
        app_version=app_version,
        screenshot=screenshot,
    )
    return FeedbackCreatedRead(id=feedback.id)


@router.get("/admin/feedback", response_model=list[FeedbackAdminRead])
async def list_feedback_admin(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[FeedbackStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    rows = await FeedbackService(session).list_for_admin(status_filter, limit)
    return [
        FeedbackAdminRead(
            id=feedback.id,
            kind=feedback.kind,
            status=feedback.status,
            text=feedback.text,
            has_screenshot=feedback.screenshot_path is not None,
            context=feedback.context,
            created_at=feedback.created_at,
            user_id=user.id,
            user_name=f"{user.first_name} {user.last_name}".strip(),
            user_email=user.email,
        )
        for feedback, user in rows
    ]


@router.patch("/admin/feedback/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_feedback_status(
    feedback_id: uuid.UUID,
    body: FeedbackStatusUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await FeedbackService(session).set_status(feedback_id, body.status)


@router.get("/admin/feedback/{feedback_id}/screenshot")
async def get_feedback_screenshot(
    feedback_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Admin-only: screenshots live outside static/ on purpose."""
    return FileResponse(await FeedbackService(session).screenshot_file(feedback_id))
