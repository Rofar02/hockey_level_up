"""Weekly tasks from the coach (2026-10-09, release plan step 7) -- see
app.core.coach_tasks. Tasks are stored per (player, week); progress is
counted on read from what already exists (the activity calendar, the
diary), the same "check on read" approach as QuestService.
"""
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.coach_tasks import (
    COACH_TASK_XP,
    MAX_TASKS_PER_WEEK,
    CoachTaskSpec,
    CoachTaskType,
    parse_spec,
    task_title,
    template_specs,
)
from app.core.ice_focus import ICE_FOCUSES
from app.models.coach_task import WeeklyCoachTask
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.schemas.quest import CoachTaskRead
from app.services.quest_service import QuestService
from app.services.streak_service import TRAINING_SESSION_TYPES, list_activity_calendar

logger = logging.getLogger(__name__)

AI_TASKS_INSTRUCTIONS = (
    "Выбери игроку 2-3 задания на новую неделю по его данным. Ответь ТОЛЬКО JSON-массивом "
    "без пояснений, элементы вида {\"type\": ..., \"count\": ..., \"focus_id\": ...}. Типы: "
    "\"complete_trainings\" (закрыть N тренировок, N 1-7), \"ice_reports\" (N отчётов после льда/игр, "
    "1-7), \"no_missed_day\" (неделя без пропусков, без count), \"days_in_a_row\" (N тренировочных "
    "дней подряд, 2-7), \"ice_focus\" (держать фокус на N льдах и отметить в отчёте, 1-5; focus_id "
    "-- один из списка ниже или не указывать). Никаких заданий на вес или повторы. Задания должны "
    "быть выполнимы по плану игрока, без перегруза."
)


@dataclass(frozen=True)
class WeekPlanCaps:
    """What this week's plan makes possible -- a task's target is cut to it
    on read, so a task stays doable after the plan changes (and an AI task
    saved before the plan existed fits it once it does)."""

    has_plan: bool
    trainings: int  # ice + gym days, a double day's extra gym not counted
    ice_like: int  # ice days and games -- the days with a report
    ice_days: int  # ice days only -- the days with a focus (games have none)
    longest_run: int  # most training days in a row

    def target(self, spec: CoachTaskSpec) -> int | None:
        """The target to show, or None when the plan leaves no room for it."""
        if not self.has_plan:
            return spec.count if spec.type != CoachTaskType.NO_MISSED_DAY else 1
        if spec.type == CoachTaskType.COMPLETE_TRAININGS:
            cap = self.trainings
        elif spec.type == CoachTaskType.ICE_REPORTS:
            cap = self.ice_like
        elif spec.type == CoachTaskType.ICE_FOCUS:
            cap = self.ice_days
        elif spec.type == CoachTaskType.DAYS_IN_A_ROW:
            cap = self.longest_run if self.longest_run >= 2 else 0
        else:
            return 1 if self.trainings > 0 else None
        return min(spec.count, cap) if cap > 0 else None


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _local_today(user: User) -> date:
    try:
        return datetime.now(ZoneInfo(user.timezone or "UTC")).date()
    except Exception:
        return datetime.now(timezone.utc).date()


class CoachTaskService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_week(self, user: User, today: date | None = None) -> list[CoachTaskRead]:
        """This week's tasks with progress; free players get template tasks
        the first time they look, built off this week's plan."""
        today = today or _local_today(user)
        week_start = _monday(today)
        caps = await self._plan_caps(user.id, week_start)
        tasks = await self._tasks(user.id, week_start)
        if not tasks:
            await self.save_specs(user.id, week_start, template_specs(caps.trainings, caps.ice_like), "template")
            tasks = await self._tasks(user.id, week_start)
        reads = [await self._read(user.id, task, week_start, today, caps) for task in tasks]
        return [read for read in reads if read is not None]

    async def claim(self, user: User, task_id: uuid.UUID) -> CoachTaskRead:
        today = _local_today(user)
        week_start = _monday(today)
        task = await self._session.get(WeeklyCoachTask, task_id)
        if task is None or task.user_id != user.id or task.week_start != week_start:
            raise HTTPException(status_code=404, detail="Задание не найдено")
        caps = await self._plan_caps(user.id, week_start)
        read = await self._read(user.id, task, week_start, today, caps)
        if read is None or task.claimed_at is not None or not read.done:
            raise HTTPException(status_code=400, detail="Задание ещё не выполнено или уже получено")
        # Atomic: of two taps at once only the one that really sets
        # claimed_at grants the XP.
        claimed = await self._session.execute(
            update(WeeklyCoachTask)
            .where(WeeklyCoachTask.id == task.id, WeeklyCoachTask.claimed_at.is_(None))
            .values(claimed_at=func.now())
            .returning(WeeklyCoachTask.id)
        )
        if claimed.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Задание ещё не выполнено или уже получено")
        await QuestService(self._session)._grant_xp(user.id, COACH_TASK_XP)
        await self._session.commit()
        await self._session.refresh(task)
        return await self._read(user.id, task, week_start, today, caps)

    async def save_specs(self, user_id: uuid.UUID, week_start: date, specs: list[CoachTaskSpec], source: str) -> None:
        """At most MAX_TASKS_PER_WEEK tasks in the week, counting the ones
        already there."""
        room = MAX_TASKS_PER_WEEK - len(await self._tasks(user_id, week_start))
        for spec in specs[: max(room, 0)]:
            await self._session.execute(
                pg_insert(WeeklyCoachTask)
                .values(
                    user_id=user_id,
                    week_start=week_start,
                    task_type=spec.type.value,
                    count=spec.count,
                    focus_id=spec.focus_id,
                    source=source,
                )
                .on_conflict_do_nothing(constraint="uq_weekly_coach_tasks_user_week_type")
            )
        await self._session.commit()

    async def save_ai_reply(self, user_id: uuid.UUID, week_start: date, reply_text: str) -> int:
        """The AI coach's tasks for the week (premium, with the weekly
        review). Unknown or out-of-range tasks are dropped; nothing usable
        -> templates fill in later, on the first look. Returns how many."""
        text = reply_text.strip()
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            return 0
        try:
            raw = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return 0
        if not isinstance(raw, list):
            return 0
        specs: list[CoachTaskSpec] = []
        for item in raw:
            spec = parse_spec(item)
            if spec is not None and all(s.type != spec.type for s in specs):
                specs.append(spec)
        if not specs:
            return 0
        # The coach's tasks replace the template ones not yet claimed.
        await self._session.execute(
            delete(WeeklyCoachTask).where(
                WeeklyCoachTask.user_id == user_id,
                WeeklyCoachTask.week_start == week_start,
                WeeklyCoachTask.source == "template",
                WeeklyCoachTask.claimed_at.is_(None),
            )
        )
        before = len(await self._tasks(user_id, week_start))
        await self.save_specs(user_id, week_start, specs, "coach")
        return len(await self._tasks(user_id, week_start)) - before

    @staticmethod
    def ai_focus_list() -> str:
        return "; ".join(f"{focus.id} -- {focus.title}" for focus in ICE_FOCUSES)

    async def _tasks(self, user_id: uuid.UUID, week_start: date) -> list[WeeklyCoachTask]:
        return list(
            (
                await self._session.scalars(
                    select(WeeklyCoachTask)
                    .where(WeeklyCoachTask.user_id == user_id, WeeklyCoachTask.week_start == week_start)
                    .order_by(WeeklyCoachTask.created_at, WeeklyCoachTask.task_type)
                )
            ).all()
        )

    async def _plan_caps(self, user_id: uuid.UUID, week_start: date) -> WeekPlanCaps:
        """The week's main days only -- a double day's extra gym (step 6)
        is not a day of its own in the calendar the tasks are counted on."""
        rows = (
            await self._session.execute(
                select(DayPlan.date, DayPlan.session_type)
                .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
                .where(
                    WeeklyPlan.user_id == user_id,
                    DayPlan.date >= week_start,
                    DayPlan.date <= week_start + timedelta(days=6),
                    DayPlan.is_extra.is_(False),
                )
            )
        ).all()
        training_dates = sorted(day for day, kind in rows if kind in TRAINING_SESSION_TYPES)
        longest = run = 0
        for index, day in enumerate(training_dates):
            run = run + 1 if index and (day - training_dates[index - 1]).days == 1 else 1
            longest = max(longest, run)
        return WeekPlanCaps(
            has_plan=bool(rows),
            trainings=len(training_dates),
            ice_like=sum(1 for _, kind in rows if kind in (DaySessionType.ON_ICE, DaySessionType.GAME)),
            ice_days=sum(1 for _, kind in rows if kind == DaySessionType.ON_ICE),
            longest_run=longest,
        )

    async def _read(
        self, user_id: uuid.UUID, task: WeeklyCoachTask, week_start: date, today: date, caps: WeekPlanCaps
    ) -> CoachTaskRead | None:
        """None: the week's plan leaves no room for this task -- hidden,
        unless its XP was already claimed."""
        spec = CoachTaskSpec(CoachTaskType(task.task_type), task.count, task.focus_id)
        capped = caps.target(spec)
        if capped is None and task.claimed_at is None:
            return None
        spec = CoachTaskSpec(spec.type, capped or spec.count, spec.focus_id)
        progress, target = await self._progress(user_id, spec, week_start, today)
        return CoachTaskRead(
            id=task.id,
            type=spec.type,
            title=task_title(spec),
            source=task.source,
            progress=min(progress, target),
            target=target,
            done=progress >= target,
            claimed=task.claimed_at is not None,
            xp_reward=COACH_TASK_XP,
        )

    async def _progress(self, user_id: uuid.UUID, spec: CoachTaskSpec, week_start: date, today: date) -> tuple[int, int]:
        week_end = week_start + timedelta(days=6)
        if spec.type in (CoachTaskType.COMPLETE_TRAININGS, CoachTaskType.NO_MISSED_DAY, CoachTaskType.DAYS_IN_A_ROW):
            days = await list_activity_calendar(self._session, user_id, week_start, min(today, week_end))
            training = [d for d in days if d.session_type in TRAINING_SESSION_TYPES]
            if spec.type == CoachTaskType.COMPLETE_TRAININGS:
                return sum(1 for d in training if d.fully_completed), spec.count
            if spec.type == CoachTaskType.NO_MISSED_DAY:
                # Judged at the end of the week; until then it shows the
                # days kept so far.
                kept = sum(1 for d in training if d.fully_completed)
                planned_all = len(
                    [d for d in await list_activity_calendar(self._session, user_id, week_start, week_end) if d.session_type in TRAINING_SESSION_TYPES]
                )
                missed = any(not d.fully_completed and d.date < today for d in training)
                if missed or planned_all == 0:
                    return 0, max(planned_all, 1)
                return kept, planned_all
            best = run = 0
            previous: date | None = None
            for day in sorted(training, key=lambda d: d.date):
                if day.fully_completed:
                    run = run + 1 if previous is not None and (day.date - previous).days == 1 else 1
                    previous = day.date
                    best = max(best, run)
                else:
                    run, previous = 0, None
            return best, spec.count

        entries = (
            await self._session.scalars(
                select(TrainingDiaryEntry)
                .join(TrainingSession, TrainingSession.id == TrainingDiaryEntry.training_session_id)
                .join(DayPlan, DayPlan.id == TrainingSession.day_plan_id)
                .where(
                    TrainingDiaryEntry.user_id == user_id,
                    DayPlan.date >= week_start,
                    DayPlan.date <= week_end,
                    TrainingDiaryEntry.reported_at.is_not(None),
                    TrainingDiaryEntry.skipped.is_(False),
                )
            )
        ).all()
        if spec.type == CoachTaskType.ICE_REPORTS:
            return len(entries), spec.count
        held = [
            e for e in entries
            if e.focus_result is not None and (spec.focus_id is None or e.focus_id == spec.focus_id)
        ]
        return len(held), spec.count
