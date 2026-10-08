import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import TargetStat
from app.models.progress import StatHistory
from app.models.schedule import DaySessionType, TrainingSession
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.repositories.schedule_repository import ScheduleRepository
from app.repositories.training_diary_repository import TrainingDiaryRepository
from app.schemas.training_diary import TrainingDiaryEntryListItem
from app.services.stat_award import credit_stats
from app.services.team_event_service import TeamEventService

_DIARY_ELIGIBLE_SESSION_TYPES = (DaySessionType.ON_ICE, DaySessionType.GAME)

# 2026-10-08: the app has no exercises for an ice day or a game, so these
# stats (intellect above all -- the catalog has almost nothing for it) barely
# grew. Writing the day's diary is what earns them: a real note (at least
# DIARY_REWARD_MIN_CHARS, "Не буду писать" earns nothing) for a day that has
# already come, once per session. Base gains before diminishing returns; an
# off-ice exercise gives ~0.5-1 per stat, a day is worth a few of those.
DIARY_REWARD_MIN_CHARS = 20
DIARY_STAT_REWARDS: dict[DaySessionType, dict[TargetStat, float]] = {
    DaySessionType.ON_ICE: {
        TargetStat.ON_ICE_SKATING: 2.0,
        TargetStat.PUCK_HANDLING: 1.5,
        TargetStat.INTELLECT: 1.0,
    },
    DaySessionType.GAME: {
        TargetStat.INTELLECT: 2.0,
        TargetStat.ON_ICE_SKATING: 1.5,
        TargetStat.PUCK_HANDLING: 1.0,
    },
}


def diary_reward_reason(training_session_id: uuid.UUID) -> str:
    return f"diary:{training_session_id}"


class TrainingDiaryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._diary = TrainingDiaryRepository(session)
        self._schedule = ScheduleRepository(session)

    async def _get_owned_eligible_session(
        self, user: User, training_session_id: uuid.UUID
    ) -> TrainingSession:
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
        return training_session

    async def get_entry(
        self, user: User, training_session_id: uuid.UUID
    ) -> TrainingDiaryEntry | None:
        training_session = await self._get_owned_eligible_session(user, training_session_id)
        entry = await self._diary.get_by_training_session(training_session.id)
        if entry is not None:
            entry.rewarded = await self._is_rewarded(user, training_session.id)
        return entry

    async def save_entry(
        self, user: User, training_session_id: uuid.UUID, note: str | None
    ) -> TrainingDiaryEntry:
        training_session = await self._get_owned_eligible_session(user, training_session_id)
        session_id = training_session.id

        existing = await self._diary.get_by_training_session(session_id)
        if existing is not None:
            existing.note = note
            entry = existing
        else:
            entry = TrainingDiaryEntry(user_id=user.id, training_session_id=session_id, note=note)
            await self._diary.save(entry)
            # A team training took this day over: the first diary save is
            # what credits it (stats + XP), same as the old team diary did.
            team_event_id = training_session.day_plan.team_event_id
            if team_event_id is not None:
                await TeamEventService(self._session).grant_team_training_reward(user, team_event_id, note)

        # Transient, for the response only (see TrainingDiaryEntryRead):
        # what this save credited, and whether the day has its reward.
        entry.stat_rewards = await self._maybe_reward(user, training_session, note)
        entry.rewarded = bool(entry.stat_rewards) or await self._is_rewarded(user, session_id)

        await self._session.commit()
        # created_at/updated_at are server-computed (func.now()/onupdate) --
        # never set in Python, so the ORM object doesn't actually have a
        # value for them post-commit despite expire_on_commit=False.
        # Reading either through Pydantic's synchronous model_validate (see
        # the router) tries an implicit lazy-load outside any awaited
        # context and blows up with MissingGreenlet -- explicit async
        # refresh avoids that, same pattern UserService.update_profile
        # already uses for the same reason.
        await self._session.refresh(entry)
        return entry

    async def _is_rewarded(self, user: User, training_session_id: uuid.UUID) -> bool:
        found = await self._session.scalar(
            select(StatHistory.id)
            .where(StatHistory.user_id == user.id, StatHistory.reason == diary_reward_reason(training_session_id))
            .limit(1)
        )
        return found is not None

    async def _maybe_reward(
        self, user: User, training_session: TrainingSession, note: str | None
    ) -> dict[TargetStat, float]:
        """Credits the day's stats on the first save with a real note. The
        StatHistory reason doubles as the "already rewarded" marker, so
        autosave while typing, edits and "Готово" never credit twice."""
        if note is None or len(note.strip()) < DIARY_REWARD_MIN_CHARS:
            return {}
        day_plan = training_session.day_plan
        if day_plan.date > datetime.now(ZoneInfo(user.timezone)).date():
            return {}
        if await self._is_rewarded(user, training_session.id):
            return {}
        return await credit_stats(
            self._session,
            user.id,
            DIARY_STAT_REWARDS[day_plan.session_type],
            diary_reward_reason(training_session.id),
        )

    async def list_entries(
        self, user: User, *, limit: int | None = None, only_with_notes: bool = False
    ) -> list[TrainingDiaryEntryListItem]:
        rows = await self._diary.list_for_user(user.id, limit=limit, only_with_notes=only_with_notes)
        return [
            TrainingDiaryEntryListItem(
                id=entry.id,
                training_session_id=entry.training_session_id,
                day_plan_id=day_plan_id,
                date=entry_date,
                session_type=session_type,
                note=entry.note,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )
            for entry, entry_date, session_type, day_plan_id in rows
        ]
