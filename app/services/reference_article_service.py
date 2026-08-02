import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reference_article import ReferenceArticle
from app.repositories.reference_article_repository import ReferenceArticleRepository
from app.schemas.reference_article import ReferenceArticleCreate, ReferenceArticleUpdate


class ReferenceArticleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._articles = ReferenceArticleRepository(session)

    async def list_articles(self) -> list[ReferenceArticle]:
        return await self._articles.list_articles()

    async def get_article(self, article_id: uuid.UUID) -> ReferenceArticle:
        article = await self._articles.get_by_id(article_id)
        if article is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Reference article not found"
            )
        return article

    async def create_article(self, data: ReferenceArticleCreate) -> ReferenceArticle:
        article = await self._articles.create(data)
        await self._session.commit()
        return article

    async def update_article(
        self, article_id: uuid.UUID, data: ReferenceArticleUpdate
    ) -> ReferenceArticle:
        article = await self.get_article(article_id)
        updates = data.model_dump(exclude_unset=True)
        await self._articles.update(article, updates)
        await self._session.commit()
        await self._session.refresh(article)
        return article

    async def delete_article(self, article_id: uuid.UUID) -> None:
        article = await self.get_article(article_id)
        await self._articles.delete(article)
        await self._session.commit()
