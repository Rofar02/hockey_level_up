import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import DayPlan, DaySessionType, TrainingSession
from app.models.training_diary import TrainingDiaryEntry


class TrainingDiaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_training_session(
        self, training_session_id: uuid.UUID
    ) -> TrainingDiaryEntry | None:
        result = await self._session.execute(
            select(TrainingDiaryEntry).where(
                TrainingDiaryEntry.training_session_id == training_session_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: uuid.UUID
    ) -> list[tuple[TrainingDiaryEntry, date, DaySessionType]]:
        """Every diary entry this user has ever written, newest first --
        the "open my diary and read back" view. Joined through
        TrainingSession->DayPlan for the date/session_type the list needs
        to render (see TrainingDiaryEntryListItem), rather than a second
        per-entry lookup."""
        result = await self._session.execute(
            select(TrainingDiaryEntry, DayPlan.date, DayPlan.session_type)
            .join(TrainingSession, TrainingDiaryEntry.training_session_id == TrainingSession.id)
            .join(DayPlan, TrainingSession.day_plan_id == DayPlan.id)
            .where(TrainingDiaryEntry.user_id == user_id)
            .order_by(DayPlan.date.desc())
        )
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def save(self, entry: TrainingDiaryEntry) -> TrainingDiaryEntry:
        self._session.add(entry)
        await self._session.flush()
        return entry
