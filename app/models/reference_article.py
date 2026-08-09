import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReferenceArticle(Base):
    __tablename__ = "reference_articles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Just the filename, same convention as User.avatar_path -- image_url
    # below builds the served path from it.
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    @property
    def image_url(self) -> str | None:
        if self.image_path is None:
            return None
        return f"/static/reference-articles/{self.image_path}"
