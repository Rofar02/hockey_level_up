import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.reference_article import ReferenceArticle
from app.repositories.reference_article_repository import ReferenceArticleRepository
from app.schemas.reference_article import ReferenceArticleCreate, ReferenceArticleUpdate
from app.services import image_processing

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
# Banner and inline content images alike -- downscale-only, aspect
# preserved, bounded to fit within this box rather than forced to a fixed
# size/shape (this isn't a cropped avatar).
IMAGE_MAX_DIMENSION = 1600
# Inline images referenced from `body` markdown live in their own
# subdirectory, separate from the one-per-article banner -- there can be
# many of these per article and they aren't tracked by any single DB field.
CONTENT_IMAGE_SUBDIR = "content"


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

    async def update_image(self, article_id: uuid.UUID, file: UploadFile) -> ReferenceArticle:
        article = await self.get_article(article_id)

        upload_dir = Path(get_settings().reference_article_image_upload_dir)
        filename = await self._process_and_save_image(file, upload_dir)

        previous_filename = article.image_path
        article.image_path = filename
        await self._session.commit()
        await self._session.refresh(article)

        if previous_filename is not None:
            image_processing.delete_image_file(upload_dir, previous_filename)

        return article

    async def delete_image(self, article_id: uuid.UUID) -> ReferenceArticle:
        article = await self.get_article(article_id)
        if article.image_path is None:
            return article

        previous_filename = article.image_path
        article.image_path = None
        await self._session.commit()
        await self._session.refresh(article)

        upload_dir = Path(get_settings().reference_article_image_upload_dir)
        image_processing.delete_image_file(upload_dir, previous_filename)

        return article

    async def upload_content_image(self, article_id: uuid.UUID, file: UploadFile) -> str:
        """For an inline image referenced from `body` markdown via
        `![](url)` -- unlike update_image (the article's one banner), this
        never touches any ReferenceArticle field. The caller (the admin
        frontend) embeds the returned URL directly into the body text, same
        as any other markdown content; nothing here tracks which article an
        image "belongs" to beyond the existence check below.
        """
        await self.get_article(article_id)

        upload_dir = Path(get_settings().reference_article_image_upload_dir) / CONTENT_IMAGE_SUBDIR
        filename = await self._process_and_save_image(file, upload_dir)
        return f"/static/reference-articles/{CONTENT_IMAGE_SUBDIR}/{filename}"

    @staticmethod
    async def _process_and_save_image(file: UploadFile, upload_dir: Path) -> str:
        content = await image_processing.read_limited(file, MAX_IMAGE_SIZE_BYTES)
        extension = image_processing.detect_image_extension(content)
        image = image_processing.open_oriented(content)

        width, height = image.size
        if max(width, height) > IMAGE_MAX_DIMENSION:
            scale = IMAGE_MAX_DIMENSION / max(width, height)
            image = image.resize(
                (round(width * scale), round(height * scale)), Image.Resampling.LANCZOS
            )

        processed = image_processing.encode(image, extension)
        return image_processing.save_new_image_file(upload_dir, processed, extension)
