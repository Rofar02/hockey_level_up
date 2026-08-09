"""Shared image-upload plumbing: size-limited reads, real-format detection
(via Pillow, never the client's filename/Content-Type), EXIF orientation
correction, and disk persistence with server-generated filenames.

Originally lived inline in UserService.update_avatar (avatars only); pulled
out here so ReferenceArticleService's cover-image upload can reuse the same
validation/EXIF handling without duplicating it. What's deliberately *not*
shared: the avatar's square center-crop and the article image's
max-dimension downscale are different framings (circular avatar vs.
rectangular banner) and stay in their respective services.
"""
import io
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

READ_CHUNK_SIZE = 1024 * 1024

# Keyed by the format Pillow reports after actually decoding the file --
# never by the client's filename extension or Content-Type header, both of
# which are attacker-controlled and easy to fake.
ALLOWED_IMAGE_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
SAVE_FORMAT_BY_EXTENSION = {extension: fmt for fmt, extension in ALLOWED_IMAGE_FORMATS.items()}


async def read_limited(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(READ_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            # Abort as soon as the running total crosses the limit, rather
            # than reading the rest of a huge upload into memory just to
            # reject it afterwards.
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large -- max {max_bytes // (1024 * 1024)}MB",
            )
        chunks.append(chunk)

    if total == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    return b"".join(chunks)


def detect_image_extension(content: bytes) -> str:
    try:
        probe = Image.open(io.BytesIO(content))
        probe.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not a valid image",
        ) from exc

    # verify() leaves the parser in a state that can't be read further, so
    # re-open the same bytes to read the detected format.
    image = Image.open(io.BytesIO(content))
    extension = ALLOWED_IMAGE_FORMATS.get(image.format or "")
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image type -- only JPEG, PNG, or WEBP are allowed",
        )
    return extension


def open_oriented(content: bytes) -> Image.Image:
    """Decode + apply EXIF orientation. Mobile camera photos are frequently
    stored as upright pixels + an EXIF orientation tag -- callers that crop
    or resize need this applied first so the result matches what the user
    actually sees, not the raw sensor orientation."""
    image = Image.open(io.BytesIO(content))
    return ImageOps.exif_transpose(image)


def encode(image: Image.Image, extension: str) -> bytes:
    save_format = SAVE_FORMAT_BY_EXTENSION[extension]
    if save_format == "JPEG" and image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    output = io.BytesIO()
    image.save(output, format=save_format)
    return output.getvalue()


def save_new_image_file(upload_dir: Path, content: bytes, extension: str) -> str:
    """Writes `content` under a fresh server-generated filename and returns
    it. Never uses the client's original filename (path traversal)."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}.{extension}"
    (upload_dir / filename).write_bytes(content)
    return filename


def delete_image_file(upload_dir: Path, filename: str) -> None:
    (upload_dir / filename).unlink(missing_ok=True)
