import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import require_admin
from app.schemas.reference_article import (
    ReferenceArticleCreate,
    ReferenceArticleRead,
    ReferenceArticleSummaryRead,
    ReferenceArticleUpdate,
)
from app.services.reference_article_service import ReferenceArticleService

router = APIRouter(prefix="/reference-articles", tags=["reference-articles"])


@router.get("", response_model=list[ReferenceArticleSummaryRead])
async def list_reference_articles(session: Annotated[AsyncSession, Depends(get_db)]):
    return await ReferenceArticleService(session).list_articles()


@router.get("/{article_id}", response_model=ReferenceArticleRead)
async def get_reference_article(
    article_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)]
):
    return await ReferenceArticleService(session).get_article(article_id)


@router.post("", response_model=ReferenceArticleRead, status_code=status.HTTP_201_CREATED)
async def create_reference_article(
    body: ReferenceArticleCreate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ReferenceArticleService(session).create_article(body)


@router.patch("/{article_id}", response_model=ReferenceArticleRead)
async def update_reference_article(
    article_id: uuid.UUID,
    body: ReferenceArticleUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ReferenceArticleService(session).update_article(article_id, body)


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reference_article(
    article_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await ReferenceArticleService(session).delete_article(article_id)
