import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.feedback import FeedbackKind, FeedbackStatus


class FeedbackCreatedRead(BaseModel):
    id: uuid.UUID


class FeedbackAdminRead(BaseModel):
    id: uuid.UUID
    kind: FeedbackKind
    status: FeedbackStatus
    text: str
    has_screenshot: bool
    context: dict
    created_at: datetime
    user_id: uuid.UUID
    user_name: str
    user_email: str


class FeedbackStatusUpdate(BaseModel):
    status: FeedbackStatus
