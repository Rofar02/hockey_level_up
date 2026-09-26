"""The Analytics screen in one response (GET /users/me/analytics/overview):
findings with a next step, the six stats with the blocks skipped for each,
personal records, regularity, weekly load and muscle balance.

Everything is derived from data the app already records -- day plans and
their blocks (done / skipped / left undone), per-set logs (weight, reps,
time, the player's own "легко/тяжело" rating), exercise muscle and pattern
tags, stat history, the streak and team attendance. Nothing is stored.
"""
import math
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.exercise import (
    Exercise,
    ExerciseMovementPattern,
    ExerciseMuscleGroup,
    ExerciseTargetStat,
    MovementPattern,
    MuscleGroup,
    TargetStat,
    TrainingPhase,
)
from app.models.progress import TrainingStreak
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion, SetFeedback
from app.models.team_event import (
    TeamEvent,
    TeamEventAttendance,
    TeamEventAttendanceStatus,
    TeamEventStatus,
    TeamEventType,
)
from app.models.user import User
from app.repositories.progress_repository import ProgressRepository
from app.repositories.team_repository import TeamRepository
from app.schemas.analytics import (
    AnalyticsBalanceRead,
    AnalyticsCalendarDayRead,
    AnalyticsInsightRead,
    AnalyticsLoadRead,
    AnalyticsLoadWeekRead,
    AnalyticsMuscleShareRead,
    AnalyticsOverviewRead,
    AnalyticsRecordRead,
    AnalyticsRegularityRead,
    AnalyticsSkippedExerciseRead,
    AnalyticsStatRead,
)
from app.services.analytics_service import DECLINE_REASON_DECAY, AnalyticsService
from app.services.coach_chat_service import STAT_LABELS
from app.services.skill_service import SkillService
from app.services.stat_service import get_idle_days, is_decay_active

TRAINING_DAY_TYPES = (DaySessionType.OFF_ICE, DaySessionType.ON_ICE)
# The part of a session the player chose the content of -- warmup/cooldown
# are routine and skippable by design, so they say nothing about the plan.
MAIN_PHASES = (TrainingPhase.MAIN, TrainingPhase.PUCK)
CALENDAR_WEEKS = 4

MUSCLE_DISPLAY_GROUP: dict[MuscleGroup, str] = {
    MuscleGroup.QUADS: "legs",
    MuscleGroup.HAMSTRINGS: "legs",
    MuscleGroup.GLUTES: "legs",
    MuscleGroup.CALVES: "legs",
    MuscleGroup.CORE: "core",
    MuscleGroup.BACK: "back",
    MuscleGroup.CHEST: "chest_shoulders",
    MuscleGroup.SHOULDERS: "chest_shoulders",
    MuscleGroup.FOREARMS: "arms",
}
DISPLAY_GROUP_ORDER = ["legs", "core", "back", "chest_shoulders", "arms"]

# Thresholds for the load warning: the week's work went up noticeably AND
# the player's own ratings say it's getting too hard.
LOAD_GROWTH_WARNING = 0.10
HARD_SHARE_WARNING = 0.35
HARD_SHARE_JUMP = 0.08
HARD_SHARE_ALARM = 0.5
# Pull vs push outside this ratio is worth a note.
BALANCE_RATIO = 1.5
MIN_BLOCKS_FOR_BALANCE = 6

# Stat names differ in gender (интеллект, владение шайбой) -- the verb and
# pronoun of "X просела, пропущено N блоков на неё" agree with each.
STAT_DECLINE_WORDS: dict[TargetStat, tuple[str, str]] = {
    TargetStat.STRENGTH: ("просела", "неё"),
    TargetStat.AGILITY: ("просела", "неё"),
    TargetStat.INTELLECT: ("просел", "него"),
    TargetStat.ENDURANCE: ("просела", "неё"),
    TargetStat.ON_ICE_SKATING: ("просела", "неё"),
    TargetStat.PUCK_HANDLING: ("просело", "него"),
}


@dataclass
class _Day:
    plan: DayPlan
    main_blocks: list[SessionBlock]
    done: bool


def _plural(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def _format_number(value: float) -> str:
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def format_record_value(value: float, unit: str) -> str:
    if unit == "kg":
        return f"{_format_number(value)} кг"
    if unit == "seconds":
        total = int(round(value))
        return f"{total // 60}:{total % 60:02d}"
    return str(int(round(value)))


def _set_metric(entry: SetCompletion) -> tuple[str, float] | None:
    """The one number a set is judged by: weight when it was lifted with
    weight, else reps, else time held."""
    if entry.weight_kg is not None and entry.weight_kg > 0:
        return "kg", entry.weight_kg
    if entry.reps_completed is not None and entry.reps_completed > 0:
        return "reps", float(entry.reps_completed)
    if entry.duration_seconds_completed is not None and entry.duration_seconds_completed > 0:
        return "seconds", float(entry.duration_seconds_completed)
    return None


class AnalyticsOverviewService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_overview(self, user: User, days: int) -> AnalyticsOverviewRead:
        tz = ZoneInfo(user.timezone)
        now = datetime.now(timezone.utc)
        today = now.astimezone(tz).date()
        period_start = today - timedelta(days=days - 1)
        since = now - timedelta(days=days)
        calendar_start = today - timedelta(days=today.weekday()) - timedelta(weeks=CALENDAR_WEEKS - 1)

        loaded_days = await self._load_days(user.id, min(period_start, calendar_start), today)
        period_days = [day for day in loaded_days if day.plan.date >= period_start]
        exercise_ids = {block.exercise_id for day in loaded_days for block in day.main_blocks}
        targets = await self._target_stats(exercise_ids)

        stats = await self._stats(user.id, since, now, period_days, today, targets)
        sets = await self._set_completions(user.id)
        exercises = await self._exercises({entry.exercise_id for entry in sets})
        records = self._records(sets, exercises, since, tz)
        regularity = await self._regularity(user, period_days, loaded_days, calendar_start, today, now, since)
        load = self._load(sets, calendar_start, today, tz)
        balance = await self._balance(period_days)
        insights = await self._insights(user, days, since, now, stats, records, regularity)

        return AnalyticsOverviewRead(
            days=days,
            insights=insights,
            stats=stats,
            records=records,
            regularity=regularity,
            load=load,
            balance=balance,
        )

    # -- data --

    async def _load_days(self, user_id: uuid.UUID, start: date, end: date) -> list[_Day]:
        rows = await self._session.scalars(
            select(DayPlan)
            .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
            .where(WeeklyPlan.user_id == user_id, DayPlan.date >= start, DayPlan.date <= end)
            .options(
                selectinload(DayPlan.training_session)
                .selectinload(TrainingSession.blocks)
                .selectinload(SessionBlock.exercise)
            )
            .order_by(DayPlan.date)
        )
        days = []
        for plan in rows:
            blocks = plan.training_session.blocks if plan.training_session is not None else []
            days.append(
                _Day(
                    plan=plan,
                    main_blocks=[block for block in blocks if block.phase in MAIN_PHASES],
                    done=any(block.completed_at is not None for block in blocks),
                )
            )
        return days

    async def _target_stats(self, exercise_ids: set[uuid.UUID]) -> dict[uuid.UUID, set[TargetStat]]:
        if not exercise_ids:
            return {}
        rows = await self._session.execute(
            select(ExerciseTargetStat.exercise_id, ExerciseTargetStat.target_stat).where(
                ExerciseTargetStat.exercise_id.in_(exercise_ids)
            )
        )
        targets: dict[uuid.UUID, set[TargetStat]] = defaultdict(set)
        for exercise_id, stat in rows:
            targets[exercise_id].add(stat)
        return targets

    async def _set_completions(self, user_id: uuid.UUID) -> list[SetCompletion]:
        rows = await self._session.scalars(
            select(SetCompletion).where(SetCompletion.user_id == user_id).order_by(SetCompletion.completed_at)
        )
        return list(rows)

    async def _exercises(self, exercise_ids: set[uuid.UUID]) -> dict[uuid.UUID, Exercise]:
        if not exercise_ids:
            return {}
        rows = await self._session.scalars(select(Exercise).where(Exercise.id.in_(exercise_ids)))
        return {exercise.id: exercise for exercise in rows}

    # -- stats --

    @staticmethod
    def _missed(day: _Day, today: date) -> list[SessionBlock]:
        """Main-part blocks left undone on a training day that is over."""
        if day.plan.session_type not in TRAINING_DAY_TYPES or day.plan.date >= today:
            return []
        return [block for block in day.main_blocks if block.completed_at is None and block.skipped_at is None]

    async def _stats(
        self,
        user_id: uuid.UUID,
        since: datetime,
        now: datetime,
        period_days: list[_Day],
        today: date,
        targets: dict[uuid.UUID, set[TargetStat]],
    ) -> list[AnalyticsStatRead]:
        deltas = {
            candidate.stat_type: candidate.mover
            for candidate in await AnalyticsService(self._session).stat_deltas(user_id, since, now)
        }
        skipped: dict[TargetStat, list[date]] = defaultdict(list)
        planned: Counter[TargetStat] = Counter()
        for day in period_days:
            if day.plan.session_type not in TRAINING_DAY_TYPES or day.plan.date > today:
                continue
            missed = {block.id for block in self._missed(day, today)}
            for block in day.main_blocks:
                for stat in targets.get(block.exercise_id, ()):
                    planned[stat] += 1
                    if block.id in missed:
                        skipped[stat].append(day.plan.date)
        return [
            AnalyticsStatRead(
                stat=stat.value,
                current_value=deltas[stat].current_value,
                delta=deltas[stat].delta,
                skipped_dates=skipped.get(stat, []),
                planned_blocks=planned.get(stat, 0),
            )
            for stat in TargetStat
        ]

    # -- records --

    @staticmethod
    def _records(
        sets: list[SetCompletion], exercises: dict[uuid.UUID, Exercise], since: datetime, tz: ZoneInfo
    ) -> list[AnalyticsRecordRead]:
        """A record is a best set in the period that beats the best set of
        the same exercise before it, in the same unit. A first-ever set is
        not a record -- there's nothing it improved on."""
        before: dict[tuple[uuid.UUID, str], float] = {}
        during: dict[tuple[uuid.UUID, str], tuple[float, datetime]] = {}
        for entry in sets:
            metric = _set_metric(entry)
            if metric is None:
                continue
            key = (entry.exercise_id, metric[0])
            if entry.completed_at < since:
                before[key] = max(before.get(key, 0.0), metric[1])
            elif key not in during or metric[1] > during[key][0]:
                during[key] = (metric[1], entry.completed_at)

        records = []
        for (exercise_id, unit), (best, achieved_at) in during.items():
            previous = before.get((exercise_id, unit))
            exercise = exercises.get(exercise_id)
            if previous is None or best <= previous or exercise is None:
                continue
            records.append(
                AnalyticsRecordRead(
                    exercise_name=exercise.name,
                    unit=unit,
                    before=previous,
                    after=best,
                    achieved_on=achieved_at.astimezone(tz).date(),
                )
            )
        records.sort(key=lambda record: (record.after - record.before) / record.before, reverse=True)
        return records[:6]

    # -- regularity --

    async def _regularity(
        self,
        user: User,
        period_days: list[_Day],
        loaded_days: list[_Day],
        calendar_start: date,
        today: date,
        now: datetime,
        since: datetime,
    ) -> AnalyticsRegularityRead:
        # Own sessions only -- a day a team practice took over is counted
        # with the team ice below, not as a personal session.
        own = [
            day
            for day in period_days
            if day.plan.session_type in TRAINING_DAY_TYPES
            and day.plan.team_event_id is None
            and (day.plan.date < today or day.done)
        ]
        completed = sum(1 for day in own if day.done)

        by_date = {day.plan.date: day for day in loaded_days}
        calendar = []
        for offset in range(CALENDAR_WEEKS * 7):
            current = calendar_start + timedelta(days=offset)
            day = by_date.get(current)
            if current > today:
                status = "future"
            elif day is None:
                status = "none"
            elif day.plan.team_event_id is not None:
                status = "team"
            elif day.done:
                status = "done"
            elif day.plan.session_type in TRAINING_DAY_TYPES and current < today:
                status = "skipped"
            else:
                status = "rest"
            calendar.append(AnalyticsCalendarDayRead(date=current, status=status))

        # Exercises left undone on days the player did train: a choice, not
        # a missed day.
        skipped_counter: Counter[str] = Counter()
        for day in period_days:
            if day.done:
                for block in self._missed(day, today):
                    skipped_counter[block.exercise.name] += 1
        most_skipped = [
            AnalyticsSkippedExerciseRead(exercise_name=name, count=count)
            for name, count in skipped_counter.most_common(2)
            if count >= 2
        ]

        streak = await self._session.scalar(select(TrainingStreak).where(TrainingStreak.user_id == user.id))
        team_going, team_total = await self._team_ice(user.id, since, now)
        return AnalyticsRegularityRead(
            planned_sessions=len(own),
            completed_sessions=completed,
            streak_days=streak.current_streak if streak is not None else 0,
            team_going=team_going,
            team_total=team_total,
            calendar=calendar,
            most_skipped=most_skipped,
        )

    async def _team_ice(self, user_id: uuid.UUID, since: datetime, now: datetime) -> tuple[int | None, int | None]:
        membership = await TeamRepository(self._session).get_membership_for_user(user_id)
        if membership is None:
            return None, None
        events = list(
            await self._session.scalars(
                select(TeamEvent.id).where(
                    TeamEvent.team_id == membership.team_id,
                    TeamEvent.event_type == TeamEventType.TRAINING,
                    TeamEvent.status == TeamEventStatus.SCHEDULED,
                    TeamEvent.starts_at >= since,
                    TeamEvent.starts_at <= now,
                )
            )
        )
        if not events:
            return None, None
        going = await self._session.scalars(
            select(TeamEventAttendance.id).where(
                TeamEventAttendance.team_event_id.in_(events),
                TeamEventAttendance.user_id == user_id,
                TeamEventAttendance.status == TeamEventAttendanceStatus.GOING,
            )
        )
        return len(list(going)), len(events)

    # -- load --

    @staticmethod
    def _load(sets: list[SetCompletion], calendar_start: date, today: date, tz: ZoneInfo) -> AnalyticsLoadRead:
        weeks = [calendar_start + timedelta(weeks=index) for index in range(CALENDAR_WEEKS)]
        tonnage = [0.0] * CALENDAR_WEEKS
        count = [0] * CALENDAR_WEEKS
        rated = [0] * CALENDAR_WEEKS
        hard = [0] * CALENDAR_WEEKS
        for entry in sets:
            index = (entry.completed_at.astimezone(tz).date() - calendar_start).days // 7
            if not 0 <= index < CALENDAR_WEEKS:
                continue
            count[index] += 1
            if entry.weight_kg and entry.reps_completed:
                tonnage[index] += entry.weight_kg * entry.reps_completed
            if entry.feedback is not None:
                rated[index] += 1
                if entry.feedback in (SetFeedback.HARD, SetFeedback.MAX):
                    hard[index] += 1
        shares = [hard[i] / rated[i] if rated[i] else None for i in range(CALENDAR_WEEKS)]

        # The last two complete weeks -- the current one is still going.
        previous, last = CALENDAR_WEEKS - 3, CALENDAR_WEEKS - 2
        use_tonnage = tonnage[previous] > 0 and tonnage[last] > 0
        before = tonnage[previous] if use_tonnage else count[previous]
        after = tonnage[last] if use_tonnage else count[last]
        warning = None
        last_share, previous_share = shares[last], shares[previous]
        if last_share is not None and before > 0:
            growth = after / before - 1
            if (
                growth >= LOAD_GROWTH_WARNING
                and last_share >= HARD_SHARE_WARNING
                and (previous_share is None or last_share - previous_share >= HARD_SHARE_JUMP)
            ):
                warning = (
                    f"Объём прошлой недели +{round(growth * 100)}%, а «тяжело» и «максимум» — "
                    f"{round(last_share * 100)}% подходов. Не добавляй сверху плана, дай телу догнать нагрузку."
                )
        if warning is None and last_share is not None and last_share >= HARD_SHARE_ALARM:
            warning = (
                f"На прошлой неделе {round(last_share * 100)}% подходов на пределе. "
                "Если так и дальше, скажи тренеру — он сбавит."
            )
        return AnalyticsLoadRead(
            weeks=[
                AnalyticsLoadWeekRead(
                    week_start=weeks[i], tonnage_kg=round(tonnage[i], 1), sets=count[i], hard_share=shares[i]
                )
                for i in range(CALENDAR_WEEKS)
            ],
            warning=warning,
        )

    # -- balance --

    async def _balance(self, period_days: list[_Day]) -> AnalyticsBalanceRead:
        done_blocks = [block for day in period_days for block in day.main_blocks if block.completed_at is not None]
        exercise_ids = {block.exercise_id for block in done_blocks}
        weights: dict[uuid.UUID, list[tuple[MuscleGroup, float]]] = defaultdict(list)
        patterns: dict[uuid.UUID, set[MovementPattern]] = defaultdict(set)
        if exercise_ids:
            for exercise_id, group, weight in await self._session.execute(
                select(ExerciseMuscleGroup.exercise_id, ExerciseMuscleGroup.muscle_group, ExerciseMuscleGroup.weight).where(
                    ExerciseMuscleGroup.exercise_id.in_(exercise_ids)
                )
            ):
                weights[exercise_id].append((group, weight))
            for exercise_id, pattern in await self._session.execute(
                select(ExerciseMovementPattern.exercise_id, ExerciseMovementPattern.movement_pattern).where(
                    ExerciseMovementPattern.exercise_id.in_(exercise_ids)
                )
            ):
                patterns[exercise_id].add(pattern)

        totals: Counter[str] = Counter()
        pull = push = 0
        for block in done_blocks:
            for group, weight in weights.get(block.exercise_id, ()):
                display = MUSCLE_DISPLAY_GROUP.get(group)
                if display is not None:
                    totals[display] += weight
            block_patterns = patterns.get(block.exercise_id, set())
            pull += MovementPattern.PULL in block_patterns
            push += MovementPattern.PUSH in block_patterns

        grand = sum(totals.values())
        groups = [
            AnalyticsMuscleShareRead(group=group, share=totals[group] / grand)
            for group in DISPLAY_GROUP_ORDER
            if grand > 0
        ]
        note = None
        if pull + push >= MIN_BLOCKS_FOR_BALANCE:
            if push >= pull * BALANCE_RATIO:
                ratio = push / pull if pull else None
                note = (
                    "Тянущих упражнений меньше, чем толкающих"
                    + (f": 1 : {_format_number(ratio)}" if ratio is not None else "")
                    + ". Спина отстаёт — попроси тренера добавить тягу."
                )
            elif pull >= push * BALANCE_RATIO:
                ratio = pull / push if push else None
                note = (
                    "Толкающих упражнений меньше, чем тянущих"
                    + (f": 1 : {_format_number(ratio)}" if ratio is not None else "")
                    + ". Грудь и плечи отстают — попроси тренера добавить жимы."
                )
        return AnalyticsBalanceRead(groups=groups, pull_blocks=pull, push_blocks=push, note=note)

    # -- insights --

    async def _insights(
        self,
        user: User,
        days: int,
        since: datetime,
        now: datetime,
        stats: list[AnalyticsStatRead],
        records: list[AnalyticsRecordRead],
        regularity: AnalyticsRegularityRead,
    ) -> list[AnalyticsInsightRead]:
        insights = []
        period = f"{days} {_plural(days, ('день', 'дня', 'дней'))}"

        decliner = min(stats, key=lambda stat: stat.delta)
        if decliner.delta <= -1:
            label = STAT_LABELS[TargetStat(decliner.stat)]
            dropped, pronoun = STAT_DECLINE_WORDS[TargetStat(decliner.stat)]
            amount = _format_number(-decliner.delta)
            skipped = len(decliner.skipped_dates)
            if skipped > 0:
                detail = (
                    f"Пропущено {skipped} {_plural(skipped, ('блок', 'блока', 'блоков'))} на {pronoun} "
                    f"из {decliner.planned_blocks}."
                )
            else:
                detail = await self._decay_detail(user.id, TargetStat(decliner.stat), now)
            insights.append(
                AnalyticsInsightRead(
                    kind="decline",
                    tone="warning",
                    title=f"{label} {dropped} на {amount}",
                    detail=detail,
                    action="ask_coach",
                    coach_prompt=(
                        f"За последние {period} у меня {dropped} {label.lower()} на {amount}. "
                        "Почему так и что мне поменять?"
                    ),
                )
            )

        if records:
            count = len(records)
            listed = ", ".join(
                f"{record.exercise_name.lower()} {format_record_value(record.after, record.unit)}"
                for record in records[:3]
            )
            insights.append(
                AnalyticsInsightRead(
                    kind="records",
                    tone="good",
                    title=f"{count} {_plural(count, ('новый рекорд', 'новых рекорда', 'новых рекордов'))}",
                    detail=f"{listed[:1].upper()}{listed[1:]}.",
                    action="records",
                )
            )

        milestone = await self._milestone_forecast(user.id, since, days)
        if milestone is not None:
            insights.append(milestone)

        if not insights and regularity.planned_sessions >= 3 and regularity.completed_sessions == regularity.planned_sessions:
            insights.append(
                AnalyticsInsightRead(
                    kind="regularity",
                    tone="good",
                    title="Ни одной пропущенной тренировки",
                    detail=f"{regularity.completed_sessions} из {regularity.planned_sessions} за {period}.",
                )
            )
        return insights

    async def _decay_detail(self, user_id: uuid.UUID, stat: TargetStat, now: datetime) -> str:
        user_stat = await ProgressRepository(self._session).get_user_stat(user_id, stat)
        if user_stat is not None and is_decay_active(get_idle_days(user_stat, now), stat):
            return DECLINE_REASON_DECAY
        return "Пропусков нет — спроси тренера, что поменять."

    async def _milestone_forecast(self, user_id: uuid.UUID, since: datetime, days: int) -> AnalyticsInsightRead | None:
        skills_service = SkillService(self._session)
        skills = await skills_service.list_skills_for_user(user_id)
        baselines = await skills_service.get_skill_baselines(user_id, since)
        best: tuple[float, AnalyticsInsightRead] | None = None
        weeks_in_period = days / 7
        for skill in skills:
            milestone = skill.next_milestone
            if milestone is None or milestone.points_remaining <= 0:
                continue
            weekly = (skill.value - baselines.get(skill.id, 0.0)) / weeks_in_period
            if weekly <= 0.05:
                continue
            weeks = math.ceil(milestone.points_remaining / weekly)
            if weeks > 26:
                continue
            insight = AnalyticsInsightRead(
                kind="milestone",
                tone="neutral",
                title=f"«{skill.name}» — до следующего порога ~{weeks} {_plural(weeks, ('неделя', 'недели', 'недель'))}",
                detail=(
                    f"Сейчас {_format_number(skill.value)} из {milestone.threshold}, "
                    f"растёт на ~{_format_number(weekly)} в неделю."
                ),
            )
            if best is None or weeks < best[0]:
                best = (weeks, insight)
        return best[1] if best is not None else None
