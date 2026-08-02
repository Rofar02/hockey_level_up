import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reference_article import ReferenceArticle
from app.schemas.reference_article import ReferenceArticleCreate


class ReferenceArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_articles(self) -> list[ReferenceArticle]:
        query = select(ReferenceArticle).order_by(ReferenceArticle.category, ReferenceArticle.title)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, article_id: uuid.UUID) -> ReferenceArticle | None:
        return await self._session.get(ReferenceArticle, article_id)

    async def create(self, data: ReferenceArticleCreate) -> ReferenceArticle:
        article = ReferenceArticle(**data.model_dump())
        self._session.add(article)
        await self._session.flush()
        return article

    async def update(self, article: ReferenceArticle, updates: dict) -> ReferenceArticle:
        for field, value in updates.items():
            setattr(article, field, value)
        await self._session.flush()
        return article

    async def delete(self, article: ReferenceArticle) -> None:
        await self._session.delete(article)
        await self._session.flush()
