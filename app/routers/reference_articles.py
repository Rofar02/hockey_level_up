import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import require_admin
from app.schemas.reference_article import (
    ReferenceArticleCreate,
    ReferenceArticleImageUploadRead,
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


@router.post("/{article_id}/image", response_model=ReferenceArticleRead)
async def upload_reference_article_image(
    article_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
):
    return await ReferenceArticleService(session).update_image(article_id, file)


@router.delete("/{article_id}/image", response_model=ReferenceArticleRead)
async def delete_reference_article_image(
    article_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    # Returns the updated article (200), not 204 -- unlike DELETE
    # /{article_id} above (which removes the whole row), this only clears
    # one field, and handing back the fresh state saves the admin UI a
    # refetch after a "remove image" click.
    return await ReferenceArticleService(session).delete_image(article_id)


@router.post("/{article_id}/content-image", response_model=ReferenceArticleImageUploadRead)
async def upload_reference_article_content_image(
    article_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
):
    """Separate from POST /{article_id}/image (the one-per-article banner)
    -- this is for images referenced inline from `body` markdown via
    `![](url)`. Doesn't update the article row at all; the admin frontend
    inserts the returned url into the body text itself."""
    url = await ReferenceArticleService(session).upload_content_image(article_id, file)
    return ReferenceArticleImageUploadRead(url=url)
