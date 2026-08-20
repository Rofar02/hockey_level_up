"""TeamService.update_logo -- captain-only emblem upload, reusing the same
image_processing pipeline as UserService.update_avatar (square center-crop,
downscale-only resize, server-generated filename, old file deleted only
after the new one is committed).

team_logo_upload_dir is monkeypatched to pytest's tmp_path so this never
touches the real static/team-logos directory -- pytest cleans tmp_path up
automatically, unlike the DB (rolled back via db_session's savepoint).
"""
import io
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from app.models.user import User
from app.services import team_service as team_service_module
from app.services.team_service import TeamService


@pytest.fixture(autouse=True)
def _team_logo_tmp_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        team_service_module,
        "get_settings",
        lambda: SimpleNamespace(team_logo_upload_dir=str(tmp_path)),
    )
    return tmp_path


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"logo_{unique}",
        email=f"logo_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_upload_file(*, size: tuple[int, int] = (800, 600), fmt: str = "PNG") -> UploadFile:
    buffer = io.BytesIO()
    Image.new("RGB", size, color="blue").save(buffer, format=fmt)
    buffer.seek(0)
    return UploadFile(filename=f"logo.{fmt.lower()}", file=buffer)


@pytest.mark.asyncio
async def test_captain_can_upload_team_logo(db_session, tmp_path) -> None:
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")

    updated = await service.update_logo(captain, team.id, _make_upload_file())

    assert updated.logo_url is not None
    assert updated.logo_url.startswith("/static/team-logos/")
    saved_files = list(tmp_path.iterdir())
    assert len(saved_files) == 1


@pytest.mark.asyncio
async def test_non_captain_cannot_upload_team_logo(db_session) -> None:
    captain = _make_user()
    player = _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")
    request = await service.join_by_code(player, team.invite_code)
    await service.approve_request(captain, request.id)

    with pytest.raises(HTTPException) as exc_info:
        await service.update_logo(player, team.id, _make_upload_file())
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_uploading_a_new_logo_deletes_the_old_file(db_session, tmp_path) -> None:
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")

    await service.update_logo(captain, team.id, _make_upload_file())
    assert len(list(tmp_path.iterdir())) == 1

    await service.update_logo(captain, team.id, _make_upload_file())
    # The first file was deleted once the second was committed -- exactly
    # one file survives, not two.
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.asyncio
async def test_heic_upload_from_iphone_is_accepted_and_saved_as_jpg(db_session, tmp_path) -> None:
    """iPhone Camera Roll photos are frequently HEIC -- image_processing
    registers pillow_heif's opener so these decode instead of 400ing, and
    always re-saves as an actual .jpg (never .heic, which other browsers
    can't render in an <img> tag) regardless of the source format.
    """
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")

    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), color="green").save(buffer, format="HEIF")
    buffer.seek(0)
    heic_file = UploadFile(filename="IMG_0001.heic", file=buffer)

    updated = await service.update_logo(captain, team.id, heic_file)

    assert updated.logo_url is not None
    assert updated.logo_url.endswith(".jpg")
    saved_files = list(tmp_path.iterdir())
    assert len(saved_files) == 1
    assert saved_files[0].suffix == ".jpg"


@pytest.mark.asyncio
async def test_mpo_upload_from_iphone_portrait_mode_is_accepted(db_session, tmp_path) -> None:
    """Found via a real failed upload in the wild: iPhone Portrait-mode
    photos are sometimes exported as MPO -- a JPEG container holding the
    main shot plus a depth frame -- which Pillow decodes fine (MpoImageFile
    is a JpegImageFile subclass) but wasn't in the allow-list, so every
    such photo 400ed with "Unsupported image type".
    """
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")

    buffer = io.BytesIO()
    main_frame = Image.new("RGB", (400, 300), color="orange")
    depth_frame = Image.new("RGB", (400, 300), color="gray")
    main_frame.save(buffer, format="MPO", save_all=True, append_images=[depth_frame])
    buffer.seek(0)
    mpo_file = UploadFile(filename="IMG_0002.jpg", file=buffer)

    updated = await service.update_logo(captain, team.id, mpo_file)

    assert updated.logo_url is not None
    assert updated.logo_url.endswith(".jpg")
    saved_files = list(tmp_path.iterdir())
    assert len(saved_files) == 1


@pytest.mark.asyncio
async def test_invalid_image_is_rejected(db_session) -> None:
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")

    not_an_image = UploadFile(filename="logo.png", file=io.BytesIO(b"not a real image"))
    with pytest.raises(HTTPException) as exc_info:
        await service.update_logo(captain, team.id, not_an_image)
    assert exc_info.value.status_code == 400
