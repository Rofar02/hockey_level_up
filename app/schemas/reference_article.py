import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReferenceArticleSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    category: str


class ReferenceArticleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    category: str
    body: str
    created_at: datetime


class ReferenceArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1)


class ReferenceArticleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    body: str | None = Field(default=None, min_length=1)
