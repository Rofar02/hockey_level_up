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
import logging
import uuid
from pathlib import Path

import pillow_heif
from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

# Registers a Pillow plugin so Image.open() understands HEIC/HEIF -- the
# format iPhones save Camera Roll photos in. Without this, every iPhone
# upload (avatar or team logo) that Safari didn't already transcode to JPEG
# fails detection with "not a valid image".
pillow_heif.register_heif_opener()

READ_CHUNK_SIZE = 1024 * 1024

# Keyed by the format Pillow reports after actually decoding the file --
# never by the client's filename extension or Content-Type header, both of
# which are attacker-controlled and easy to fake. HEIF and MPO both map to
# "jpg", not a format-specific extension of their own: browsers other than
# Safari can't render <img src="*.heic">, and encode() always re-saves as
# an actual JPEG for that extension regardless of the source format (see
# SAVE_FORMAT_BY_EXTENSION). MPO is what iPhone Portrait-mode photos often
# get saved/re-exported as -- a JPEG container holding the main shot plus
# a depth/disparity frame; Pillow's MpoImageFile is a JpegImageFile
# subclass and defaults to the first (main) frame, so it behaves exactly
# like a plain JPEG for every operation this pipeline does.
ALLOWED_IMAGE_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "HEIF": "jpg", "MPO": "jpg"}
SAVE_FORMAT_BY_EXTENSION = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}


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
    except (UnidentifiedImageError, OSError):
        # Logged with the magic bytes + exact exception -- "not a valid
        # image" alone isn't enough to diagnose a real-world rejection
        # after the fact (e.g. which iPhone HEIC variant/codec Pillow
        # actually choked on).
        logger.warning(
            "detect_image_extension: Pillow could not decode %d bytes "
            "(first 16 bytes: %s)",
            len(content),
            content[:16].hex(),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not a valid image",
        ) from None

    # verify() leaves the parser in a state that can't be read further, so
    # re-open the same bytes to read the detected format.
    image = Image.open(io.BytesIO(content))
    extension = ALLOWED_IMAGE_FORMATS.get(image.format or "")
    if extension is None:
        logger.warning(
            "detect_image_extension: decoded as unsupported format %r (mode=%s)",
            image.format,
            image.mode,
        )
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
