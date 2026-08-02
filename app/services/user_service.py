import io
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User
from app.schemas.user import UserUpdate

MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024
AVATAR_READ_CHUNK_SIZE = 1024 * 1024
AVATAR_TARGET_SIZE = 400

# Keyed by the format Pillow reports after actually decoding the file --
# never by the client's filename extension or Content-Type header, both of
# which are attacker-controlled and easy to fake.
ALLOWED_AVATAR_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
AVATAR_SAVE_FORMATS = {extension: fmt for fmt, extension in ALLOWED_AVATAR_FORMATS.items()}


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
        content = await self._read_limited(file)
        extension = self._detect_image_extension(content)
        processed = self._process_avatar_image(content, extension)

        upload_dir = Path(get_settings().avatar_upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Server-generated name only -- the client's original filename is
        # never used in the saved path, so it can't be used for path
        # traversal (e.g. "../../etc/passwd.jpg").
        filename = f"{uuid.uuid4()}.{extension}"
        (upload_dir / filename).write_bytes(processed)

        previous_filename = user.avatar_path
        user.avatar_path = filename
        await self._session.commit()
        await self._session.refresh(user)

        if previous_filename is not None:
            (upload_dir / previous_filename).unlink(missing_ok=True)

        return user

    @staticmethod
    async def _read_limited(file: UploadFile) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await file.read(AVATAR_READ_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_AVATAR_SIZE_BYTES:
                # Abort as soon as the running total crosses the limit,
                # rather than reading the rest of a huge upload into memory
                # just to reject it afterwards.
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large -- max {MAX_AVATAR_SIZE_BYTES // (1024 * 1024)}MB",
                )
            chunks.append(chunk)

        if total == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
        return b"".join(chunks)

    @staticmethod
    def _detect_image_extension(content: bytes) -> str:
        try:
            probe = Image.open(io.BytesIO(content))
            probe.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is not a valid image",
            ) from exc

        # verify() leaves the parser in a state that can't be read further,
        # so re-open the same bytes to read the detected format.
        image = Image.open(io.BytesIO(content))
        extension = ALLOWED_AVATAR_FORMATS.get(image.format or "")
        if extension is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported image type -- only JPEG, PNG, or WEBP are allowed",
            )
        return extension

    @staticmethod
    def _process_avatar_image(content: bytes, extension: str) -> bytes:
        image = Image.open(io.BytesIO(content))
        # Mobile camera photos are frequently stored upright pixels + an
        # EXIF orientation tag -- apply it now so the crop below is centered
        # on what the user actually sees, not the raw sensor orientation.
        image = ImageOps.exif_transpose(image)

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

        save_format = AVATAR_SAVE_FORMATS[extension]
        if save_format == "JPEG" and image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        output = io.BytesIO()
        image.save(output, format=save_format)
        return output.getvalue()
