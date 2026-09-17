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
        self, user_id: uuid.UUID, *, limit: int | None = None, only_with_notes: bool = False
    ) -> list[tuple[TrainingDiaryEntry, date, DaySessionType, uuid.UUID]]:
        """Diary entries this user has written, newest first -- the "open my
        diary and read back" view (no `limit`/`only_with_notes`, the real
        /diary page's own use, which wants every entry so the player can
        see what they left blank too). Both params exist for
        CoachChatService's system-prompt summary, which only wants the
        last few entries that actually say something -- `only_with_notes`
        filters at the DB level rather than in Python so a run of recent
        blank entries can't push real notes out of a small `limit`. Joined
        through TrainingSession->DayPlan for the date/session_type/id the
        list needs to render (see TrainingDiaryEntryListItem) -- the DayPlan
        id (2026-09-18: added so the frontend list can link each entry
        straight to that day's TrainingSessionPage, /training/<day_plan_id>)
        rather than a second per-entry lookup."""
        query = (
            select(TrainingDiaryEntry, DayPlan.date, DayPlan.session_type, DayPlan.id)
            .join(TrainingSession, TrainingDiaryEntry.training_session_id == TrainingSession.id)
            .join(DayPlan, TrainingSession.day_plan_id == DayPlan.id)
            .where(TrainingDiaryEntry.user_id == user_id)
            .order_by(DayPlan.date.desc())
        )
        if only_with_notes:
            query = query.where(TrainingDiaryEntry.note.isnot(None))
        if limit is not None:
            query = query.limit(limit)
        result = await self._session.execute(query)
        return [(row[0], row[1], row[2], row[3]) for row in result.all()]

    async def save(self, entry: TrainingDiaryEntry) -> TrainingDiaryEntry:
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_session_ids_with_entries(
        self, training_session_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        """2026-09-17 (audit item #3): bulk EXISTS check backing
        TrainingSessionRead.has_diary_entry -- a row existing at all (note
        possibly None -- see the "quiet skip" flow in TrainingDiaryEntryIn's
        caller) is enough to mark the diary step done, so this is a plain
        membership check, not a note.isnot(None) filter. Empty input short-
        circuits without a query, same convention as
        ExerciseRepository.list_target_stats_by_exercise."""
        if not training_session_ids:
            return set()
        result = await self._session.execute(
            select(TrainingDiaryEntry.training_session_id).where(
                TrainingDiaryEntry.training_session_id.in_(training_session_ids)
            )
        )
        return set(result.scalars().all())
