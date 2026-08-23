import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import DaySessionType
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.repositories.schedule_repository import ScheduleRepository
from app.repositories.training_diary_repository import TrainingDiaryRepository
from app.schemas.training_diary import TrainingDiaryEntryListItem

_DIARY_ELIGIBLE_SESSION_TYPES = (DaySessionType.ON_ICE, DaySessionType.GAME)


class TrainingDiaryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._diary = TrainingDiaryRepository(session)
        self._schedule = ScheduleRepository(session)

    async def _get_owned_eligible_session_id(
        self, user: User, training_session_id: uuid.UUID
    ) -> uuid.UUID:
        """Same ownership-check shape as
        SetCompletionService._get_owned_exercise_in_session, plus the
        ON_ICE/GAME gate -- OFF_ICE already gets rich structured feedback
        per exercise via SetCompletion, a diary there would be redundant.
        """
        training_session = await self._schedule.get_training_session_with_owner(training_session_id)
        if training_session is None or training_session.day_plan.weekly_plan.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Training session not found"
            )
        if training_session.day_plan.session_type not in _DIARY_ELIGIBLE_SESSION_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Дневник доступен только для дней на льду и игр",
            )
        return training_session.id

    async def get_entry(
        self, user: User, training_session_id: uuid.UUID
    ) -> TrainingDiaryEntry | None:
        session_id = await self._get_owned_eligible_session_id(user, training_session_id)
        return await self._diary.get_by_training_session(session_id)

    async def save_entry(
        self, user: User, training_session_id: uuid.UUID, note: str | None
    ) -> TrainingDiaryEntry:
        session_id = await self._get_owned_eligible_session_id(user, training_session_id)

        existing = await self._diary.get_by_training_session(session_id)
        if existing is not None:
            existing.note = note
            entry = existing
        else:
            entry = TrainingDiaryEntry(user_id=user.id, training_session_id=session_id, note=note)
            await self._diary.save(entry)

        await self._session.commit()
        return entry

    async def list_entries(self, user: User) -> list[TrainingDiaryEntryListItem]:
        rows = await self._diary.list_for_user(user.id)
        return [
            TrainingDiaryEntryListItem(
                id=entry.id,
                training_session_id=entry.training_session_id,
                date=entry_date,
                session_type=session_type,
                note=entry.note,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )
            for entry, entry_date, session_type in rows
        ]
