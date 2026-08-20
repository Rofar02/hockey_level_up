import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import verify_password
from app.models.exercise import EquipmentItem
from app.models.team import TeamMembership
from app.models.user import User
from app.repositories.exercise_repository import ExerciseRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserAdminUpdate, UserUpdate
from app.services import image_processing
from app.services.friend_service import FriendService

MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024
AVATAR_TARGET_SIZE = 400


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._friends = FriendService(session)
        self._exercises = ExerciseRepository(session)

    async def update_profile(self, user: User, data: UserUpdate) -> User:
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(user, field, value)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def list_owned_equipment(self, user_id: uuid.UUID) -> list[EquipmentItem]:
        return list(await self._exercises.list_owned_equipment(user_id))

    async def replace_owned_equipment(
        self, user_id: uuid.UUID, items: list[EquipmentItem]
    ) -> list[EquipmentItem]:
        unique_items = list(dict.fromkeys(items))
        await self._exercises.replace_owned_equipment(user_id, unique_items)
        await self._session.commit()
        return unique_items

    async def mark_onboarding_tour_seen(self, user: User) -> User:
        # Idempotent by design -- closing the tour a second time (e.g. a
        # retry after a dropped response) just re-sets True to True, never
        # errors.
        if not user.has_seen_onboarding_tour:
            user.has_seen_onboarding_tour = True
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

    async def delete_account(self, user: User, password: str) -> None:
        if password == "":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Password is required"
            )
        if not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Incorrect password"
            )

        avatar_path = user.avatar_path
        upload_dir = Path(get_settings().avatar_upload_dir)

        # Every other table with a user_id FK has ON DELETE CASCADE (see the
        # models under app/models/), and the schedule tree (weekly_plans ->
        # day_plans -> training_sessions -> session_blocks) cascades
        # transitively from weekly_plans.user_id -- so deleting the row here
        # is enough for the DB side; only the avatar file below needs
        # explicit cleanup since it isn't a DB row.
        await self._session.delete(user)
        await self._session.commit()

        if avatar_path is not None:
            image_processing.delete_image_file(upload_dir, avatar_path)

    async def get_public_profile(self, requester: User, target_id: uuid.UUID) -> User:
        """No open profile browsing (see the diagnosis: open name search is
        deliberately not offered to regular users) -- viewable only by
        friends and teammates, checked here rather than left to the client.
        """
        target = await self._users.get_by_id(target_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if target.id == requester.id:
            return target
        if await self._can_view_profile(requester.id, target.id):
            return target
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view the profiles of friends and teammates",
        )

    async def _can_view_profile(self, requester_id: uuid.UUID, target_id: uuid.UUID) -> bool:
        if await self._friends.are_friends(requester_id, target_id):
            return True
        return await self._share_a_team(requester_id, target_id)

    async def _share_a_team(self, requester_id: uuid.UUID, target_id: uuid.UUID) -> bool:
        requester_team_ids = select(TeamMembership.team_id).where(
            TeamMembership.user_id == requester_id
        )
        result = await self._session.execute(
            select(TeamMembership.id)
            .where(
                TeamMembership.user_id == target_id,
                TeamMembership.team_id.in_(requester_team_ids),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def list_users_admin(
        self, *, search: str | None, limit: int, offset: int
    ) -> list[User]:
        return await self._users.list_users(search=search, limit=limit, offset=offset)

    async def update_user_admin(self, user_id: uuid.UUID, data: UserAdminUpdate) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        updates = data.model_dump(exclude_unset=True)
        # Demoting is only dangerous when it actually flips a currently-admin
        # user to non-admin -- guard on the target's current state, not just
        # "is_admin present in the request", so re-sending is_admin=True (or
        # is_admin=False for someone who already isn't one) never trips it.
        if updates.get("is_admin") is False and user.is_admin:
            remaining_admins = await self._users.count_admins(exclude_user_id=user.id)
            if remaining_admins == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove admin rights from the last remaining administrator",
                )

        for field, value in updates.items():
            setattr(user, field, value)
        await self._session.commit()
        await self._session.refresh(user)
        return user
