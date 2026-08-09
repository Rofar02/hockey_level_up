from pathlib import Path

from fastapi import UploadFile
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User
from app.schemas.user import UserUpdate
from app.services import image_processing

MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024
AVATAR_TARGET_SIZE = 400


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def update_profile(self, user: User, data: UserUpdate) -> User:
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(user, field, value)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def update_avatar(self, user: User, file: UploadFile) -> User:
        content = await image_processing.read_limited(file, MAX_AVATAR_SIZE_BYTES)
        extension = image_processing.detect_image_extension(content)
        image = image_processing.open_oriented(content)

        width, height = image.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        image = image.crop((left, top, left + side, top + side))

        # Only ever shrink -- upscaling a sub-400px source would just add
        # blur, not real detail.
        if side > AVATAR_TARGET_SIZE:
            image = image.resize(
                (AVATAR_TARGET_SIZE, AVATAR_TARGET_SIZE), Image.Resampling.LANCZOS
            )

        processed = image_processing.encode(image, extension)

        upload_dir = Path(get_settings().avatar_upload_dir)
        filename = image_processing.save_new_image_file(upload_dir, processed, extension)

        previous_filename = user.avatar_path
        user.avatar_path = filename
        await self._session.commit()
        await self._session.refresh(user)

        if previous_filename is not None:
            image_processing.delete_image_file(upload_dir, previous_filename)

        return user
