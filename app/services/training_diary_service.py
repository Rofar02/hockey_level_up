import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import TargetStat
from app.models.progress import StatHistory
from app.models.schedule import DaySessionType, TrainingSession
from app.models.training_diary import GameResult, IceEffort, IceHighlight, TrainingDiaryEntry
from app.models.user import User
from app.repositories.schedule_repository import ScheduleRepository
from app.repositories.training_diary_repository import TrainingDiaryRepository
from app.schemas.training_diary import DiaryReportIn, TrainingDiaryEntryListItem
from app.services.stat_award import award_xp, credit_stats
from app.services.team_event_service import TEAM_TRAINING_XP_BONUS, TeamEventService

_DIARY_ELIGIBLE_SESSION_TYPES = (DaySessionType.ON_ICE, DaySessionType.GAME)

# 2026-10-08: the app has no exercises for an ice day or a game, so these
# stats (intellect above all -- the catalog has almost nothing for it) barely
# grew. The report after the day is what earns them: a submitted report
# ("Не был" earns nothing) for a day that has already come and at most
# REPORT_REWARD_WINDOW_DAYS old, once per session. Base gains before
# diminishing returns; an off-ice exercise gives ~0.5-1 per stat, a day is
# worth a few of those.
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
REPORT_XP: dict[DaySessionType, int] = {DaySessionType.ON_ICE: 30, DaySessionType.GAME: 40}
REPORT_REWARD_WINDOW_DAYS = 3

# An ice day's base gains scale a little with how long and how hard it was,
# and each "что шло лучше всего" pick adds a bit to its stat. A game's don't
# scale with anything the player reports: the self-rating and the counters
# must never pay, or they stop being honest.
ICE_DURATION_FACTORS: tuple[tuple[int, float], ...] = ((45, 0.85), (60, 1.0), (75, 1.1))
ICE_LONG_DURATION_FACTOR = 1.2
ICE_EFFORT_FACTORS: dict[IceEffort, float] = {IceEffort.EASY: 0.9, IceEffort.NORMAL: 1.0, IceEffort.HARD: 1.1}
ICE_HIGHLIGHT_BONUS = 0.3
ICE_HIGHLIGHT_STATS: dict[IceHighlight, TargetStat] = {
    IceHighlight.SKATING: TargetStat.ON_ICE_SKATING,
    IceHighlight.PASSING: TargetStat.PUCK_HANDLING,
    IceHighlight.SHOOTING: TargetStat.PUCK_HANDLING,
    IceHighlight.GAME_READING: TargetStat.INTELLECT,
}


def report_base_gains(session_type: DaySessionType, report: DiaryReportIn) -> dict[TargetStat, float]:
    gains = dict(DIARY_STAT_REWARDS[session_type])
    if session_type != DaySessionType.ON_ICE:
        return gains
    minutes = report.duration_minutes or 60
    factor = next((f for limit, f in ICE_DURATION_FACTORS if minutes <= limit), ICE_LONG_DURATION_FACTOR)
    factor *= ICE_EFFORT_FACTORS[report.effort or IceEffort.NORMAL]
    gains = {stat: base * factor for stat, base in gains.items()}
    for highlight in set(report.highlights):
        stat = ICE_HIGHLIGHT_STATS[highlight]
        gains[stat] = gains.get(stat, 0.0) + ICE_HIGHLIGHT_BONUS
    return {stat: round(value, 2) for stat, value in gains.items()}


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
        self,
        user: User,
        training_session_id: uuid.UUID,
        note: str | None,
        report: DiaryReportIn | None = None,
    ) -> TrainingDiaryEntry:
        training_session = await self._get_owned_eligible_session(user, training_session_id)
        session_id = training_session.id
        session_type = training_session.day_plan.session_type
        if report is not None:
            self._validate_report(session_type, report)

        existing = await self._diary.get_by_training_session(session_id)
        if existing is not None:
            existing.note = note
            entry = existing
        else:
            entry = TrainingDiaryEntry(user_id=user.id, training_session_id=session_id, note=note)
            await self._diary.save(entry)
        if report is not None:
            self._apply_report(entry, session_type, report)

        # Transient, for the response only (see TrainingDiaryEntryRead):
        # what this save credited, and whether the day has its reward.
        entry.stat_rewards, entry.xp_reward = await self._maybe_reward(user, training_session, note, report)
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

    @staticmethod
    def _validate_report(session_type: DaySessionType, report: DiaryReportIn) -> None:
        if report.skipped:
            return
        if session_type == DaySessionType.ON_ICE:
            missing = report.duration_minutes is None or report.effort is None
        else:
            missing = report.game_result is None or report.self_rating is None
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Ответьте на вопросы отчёта или отметьте «Не был»",
            )

    @staticmethod
    def _apply_report(entry: TrainingDiaryEntry, session_type: DaySessionType, report: DiaryReportIn) -> None:
        """Overwrites every report field (a re-submitted report is a full
        replacement); fields of the other day type stay None."""
        is_ice = session_type == DaySessionType.ON_ICE and not report.skipped
        is_game = session_type == DaySessionType.GAME and not report.skipped
        entry.skipped = report.skipped
        entry.duration_minutes = report.duration_minutes if is_ice else None
        entry.effort = report.effort if is_ice else None
        entry.highlights = sorted({h.value for h in report.highlights}) if is_ice else None
        entry.game_result = report.game_result if is_game else None
        entry.goals = report.goals if is_game else None
        entry.assists = report.assists if is_game else None
        entry.shots = report.shots if is_game else None
        entry.self_rating = report.self_rating if is_game else None
        entry.work_on = sorted({w.value for w in report.work_on}) if is_game else None
        entry.share_rating_with_coach = report.share_rating_with_coach if is_game else False
        if entry.reported_at is None:
            entry.reported_at = datetime.now(timezone.utc)

    async def _is_rewarded(self, user: User, training_session_id: uuid.UUID) -> bool:
        found = await self._session.scalar(
            select(StatHistory.id)
            .where(StatHistory.user_id == user.id, StatHistory.reason == diary_reward_reason(training_session_id))
            .limit(1)
        )
        return found is not None

    async def _maybe_reward(
        self,
        user: User,
        training_session: TrainingSession,
        note: str | None,
        report: DiaryReportIn | None,
    ) -> tuple[dict[TargetStat, float], int]:
        """Credits the day's stats + XP on the first submitted report. The
        StatHistory reason doubles as the "already rewarded" marker, so note
        autosaves, edits and a re-submitted report never credit twice. A
        team training's day earns the team XP in place of the report XP."""
        if report is None or report.skipped:
            return {}, 0
        day_plan = training_session.day_plan
        today = datetime.now(ZoneInfo(user.timezone)).date()
        if day_plan.date > today or day_plan.date < today - timedelta(days=REPORT_REWARD_WINDOW_DAYS):
            return {}, 0
        if await self._is_rewarded(user, training_session.id):
            return {}, 0

        xp = REPORT_XP[day_plan.session_type]
        if day_plan.team_event_id is not None and await TeamEventService(
            self._session
        ).claim_team_training_reward(user, day_plan.team_event_id, note):
            xp = TEAM_TRAINING_XP_BONUS
        credited = await credit_stats(
            self._session,
            user.id,
            report_base_gains(day_plan.session_type, report),
            diary_reward_reason(training_session.id),
        )
        await award_xp(self._session, user.id, xp)
        return credited, xp

    async def list_entries(
        self,
        user: User,
        *,
        limit: int | None = None,
        only_with_content: bool = False,
        since: date | None = None,
        until: date | None = None,
    ) -> list[TrainingDiaryEntryListItem]:
        rows = await self._diary.list_for_user(
            user.id, limit=limit, only_with_content=only_with_content, since=since, until=until
        )
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
                reported_at=entry.reported_at,
                skipped=entry.skipped,
                duration_minutes=entry.duration_minutes,
                effort=entry.effort,
                game_result=entry.game_result,
                goals=entry.goals,
                assists=entry.assists,
                shots=entry.shots,
                highlights=entry.highlights,
                self_rating=entry.self_rating,
                work_on=entry.work_on,
            )
            for entry, entry_date, session_type, day_plan_id in rows
        ]


_EFFORT_TEXT = {IceEffort.EASY: "легко", IceEffort.NORMAL: "нормально", IceEffort.HARD: "на пределе"}
_HIGHLIGHT_TEXT = {"skating": "катание", "passing": "передачи", "shooting": "броски", "game_reading": "чтение игры"}
_RESULT_TEXT = {GameResult.WIN: "победа", GameResult.DRAW: "ничья", GameResult.LOSS: "поражение"}
_WORK_ON_TEXT = {"skating": "катание", "defense": "игра в защите", "shooting": "броски", "positioning": "выбор позиции"}


def format_entry_for_coach(entry: TrainingDiaryEntryListItem) -> str:
    """One diary entry as plain facts for the AI coach's prompts (chat and
    weekly review): the report, then the note."""
    parts: list[str] = []
    if entry.skipped:
        parts.append("не был")
    elif entry.session_type == DaySessionType.ON_ICE and entry.duration_minutes is not None:
        parts.append(f"{entry.duration_minutes} мин")
        if entry.effort is not None:
            parts.append(_EFFORT_TEXT[entry.effort])
        if entry.highlights:
            parts.append("лучше всего: " + ", ".join(_HIGHLIGHT_TEXT[h] for h in entry.highlights))
    elif entry.session_type == DaySessionType.GAME and entry.game_result is not None:
        parts.append(_RESULT_TEXT[entry.game_result])
        if entry.goals is not None:
            parts.append(f"голы {entry.goals}, передачи {entry.assists or 0}, броски {entry.shots or 0}")
        if entry.self_rating is not None:
            parts.append(f"оценка себе {entry.self_rating}/5")
        if entry.work_on:
            parts.append("хочет поработать: " + ", ".join(_WORK_ON_TEXT[w] for w in entry.work_on))
    if entry.note:
        parts.append(f"«{entry.note}»")
    return ", ".join(parts) if parts else "без записи"
