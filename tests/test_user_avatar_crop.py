"""UserService.update_avatar keeps the top of a tall photo -- a centred
square crop used to cut the head off a full-length shot.
"""
import io
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import UploadFile
from PIL import Image

from app.models.user import User
from app.services import user_service as user_service_module
from app.services.user_service import UserService


@pytest.fixture(autouse=True)
def _avatar_tmp_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        user_service_module,
        "get_settings",
        lambda: SimpleNamespace(avatar_upload_dir=str(tmp_path)),
    )
    return tmp_path


def _tall_photo() -> UploadFile:
    # 400 x 1000: a red "head" band in the top 150 px, blue below.
    image = Image.new("RGB", (400, 1000), color="blue")
    image.paste((255, 0, 0), (0, 0, 400, 150))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return UploadFile(filename="me.png", file=buffer)


@pytest.mark.asyncio
async def test_tall_photo_keeps_the_head(db_session, tmp_path) -> None:
    unique = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), username=f"av_{unique}", email=f"av_{unique}@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    await UserService(db_session).update_avatar(user, _tall_photo())

    saved = Image.open(Path(tmp_path) / user.avatar_path).convert("RGB")
    assert saved.size == (400, 400)
    # The crop starts 60 px down (10% of the 600 px overflow), so the red
    # band is still there at the top -- a centred crop would start at 300.
    assert saved.getpixel((200, 20)) == (255, 0, 0)
    assert saved.getpixel((200, 300)) == (0, 0, 255)
