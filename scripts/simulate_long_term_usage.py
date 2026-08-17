"""Long-term (26-week) usage simulation, run against the REAL service layer --
not mocked, not emulated. Exercises assembly (ScheduleService), periodization
(TrainingBlockService/Phase 4), overload brakes (OverloadService/Phase 5),
set logging (SetCompletionService), block completion (SessionBlockService),
and the real block_completed event handlers (stat/streak/xp gain) exactly
the way a real request would, just without going through HTTP or a
frontend -- see docs discussion for why this is the right level to drive
the simulation from.

Run against a TEST environment / dedicated test users only:

    docker compose exec backend poetry run python scripts/simulate_long_term_usage.py

Produces scripts/simulation_report.md plus a progress trace on stdout.

-- How calendar time is simulated --

TrainingBlockService.resolve_active_block/get_or_create_and_resolve already
accept an injectable `today` (see tests/test_training_block_progression.py --
this script follows the same established pattern, just against the full
real pipeline instead of a stripped down block-only setup). The one real
gap is ScheduleService.create_weekly_plan itself, which calls
get_or_create_and_resolve(user.id) with no `today` override -- so it can't
be called directly for a historical week without contaminating the
calendar-ceiling check with the real wall clock. This script does not call
create_weekly_plan; instead it performs the same steps that method does,
by hand, with an explicit simulated `today`:

    block = await training_block_service.get_or_create_and_resolve(user.id, today=week_monday)
    block_phase = await overload_service.apply_brakes(user, block.phase)
    session = await schedule_service._build_training_session(session_type, user, block_phase)

`_build_training_session` is "private" but calling it directly from test/
simulation code is already the established pattern in this codebase (see
tests/test_schedule_service_pick_main.py, test_schedule_service_block_order.py) --
it's real assembly code, not a stub.

Nothing else needs simulated time. SessionBlock.completed_at and
SetCompletion.completed_at are intentionally left at their real wall-clock
values (never backdated): nothing in the decision logic reads their
absolute value, only IS NOT NULL / relative order within a session -- and
relative order across the whole run is preserved automatically because
this script performs actions in true simulated-chronological order. All
"when did this happen" reporting below is keyed off DayPlan.date (which
IS set to the simulated historical date) and this script's own running
log, not off real timestamps.

-- How block_completed events are applied --

SessionBlockService.complete_block writes a real OutboxEvent row in the
same transaction as completed_at; a background relay+RabbitMQ consumer
(already running in the dev backend container) would normally pick it up
and dispatch to stat_consumer/streak_consumer/xp_consumer asynchronously.
This script instead reads back the real just-written OutboxEvent payload
and calls app.events.registry.get_handlers("block_completed") directly --
the exact same handler functions the real consumer calls (see
tests/test_block_completed_idempotency.py for the same pattern) -- then
marks the row published so the live relay doesn't do redundant work. Safe
either way even if the live relay races this script: idempotency claims
are keyed on (event_id, handler_name), so whichever side gets there first
wins and the other becomes a no-op.
"""
import asyncio
import random
import sys
import time
import traceback
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.core.overload import (  # noqa: E402
    STRUCTURAL_REPLAY_LOOKBACK,
    TACTICAL_BRAKE_WINDOW,
    classify_session,
    compute_difficulty_throttle_steps,
    tactical_brake_engaged,
)
from app.core.training_block import max_difficulty_for_level  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.events.handlers import block_completed as block_completed_handlers  # noqa: E402,F401 -- registers handlers
from app.events.registry import get_handlers  # noqa: E402
from app.models.exercise import EquipmentType
from app.models.outbox import OutboxEvent
from app.models.progress import StatHistory
from app.models.schedule import BlockPhase, DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.set_completion import SetFeedback
from app.models.user import User
from app.repositories.overload_repository import OverloadRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.services.overload_service import OverloadService
from app.services.reps_suggestion_service import RepsSuggestionService
from app.services.schedule_service import ScheduleService
from app.services.session_block_service import SessionBlockService
from app.services.set_completion_service import SetCompletionService
from app.services.training_block_service import TrainingBlockService
from app.services.weight_suggestion_service import WeightSuggestionService

EVENT_TYPE = "block_completed"
WEEKS = 26
REPORT_PATH = Path(__file__).resolve().parent / "simulation_report.md"

_SESSION_TYPE_CATEGORY_DAYS = {
    # weekday offset (0=Mon..6=Sun) -> DaySessionType, for the 3x/week
    # baseline shared by scenarios 1/3/4. 2 off-ice + 1 on-ice: off-ice is
    # where the catalog actually has target_sets populated for most
    # exercises (~87% of MAIN off-ice vs ~33% on-ice, checked live against
    # the seeded dev catalog) -- an all-on-ice week would rarely clear
    # MIN_FEEDBACK_SETS_FOR_SIGNAL and never meaningfully exercise either
    # overload brake.
    0: DaySessionType.OFF_ICE,  # Mon
    2: DaySessionType.OFF_ICE,  # Wed
    4: DaySessionType.ON_ICE,  # Fri
}


# ---- report data structures ----


@dataclass
class SessionRecord:
    week_index: int
    session_ordinal: int
    day_date: date
    session_type: str
    block_phase: str
    feedback_mode: str
    feedback_counts: dict = field(default_factory=dict)
    level_after: int = 0
    xp_after: int = 0
    tactical_brake_after: bool = False
    structural_throttle_after: int = 0


@dataclass
class PhaseTransition:
    session_ordinal: int
    week_index: int
    week_monday: date
    from_block: tuple
    to_block: tuple


@dataclass
class BrakeEvent:
    kind: str  # "tactical" or "structural"
    direction: str  # "engaged"/"released" or "push"/"recover"
    session_ordinal: int
    week_index: int
    day_date: date
    detail: str


@dataclass
class LevelCheckpoint:
    week_index: int
    level: int
    xp: int
    max_difficulty: int


@dataclass
class TimingSample:
    session_ordinal: int
    resolve_seconds: float
    assembly_seconds: float


@dataclass
class ScenarioReport:
    name: str
    description: str
    user_id: uuid.UUID | None = None
    sessions: list = field(default_factory=list)
    phase_transitions: list = field(default_factory=list)
    brake_events: list = field(default_factory=list)
    level_checkpoints: list = field(default_factory=list)
    timing_samples: list = field(default_factory=list)
    exceptions: list = field(default_factory=list)
    stat_distribution: dict = field(default_factory=dict)
    wall_clock_seconds: float = 0.0
    total_sessions_completed: int = 0


# ---- setup helpers ----


async def make_test_user(session, tag: str) -> User:
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"sim_{tag}_{unique}",
        email=f"sim_{tag}_{unique}@example.com",
        password_hash="irrelevant",
        last_name="Sim",
        first_name=tag,
        equipment_access=EquipmentType.GYM,
        weight=75.0,
        height=180.0,
        age=20,
        level=1,
        xp=0,
    )
    session.add(user)
    await session.flush()
    return user


def week_monday(start: date, week_index: int) -> date:
    return start + timedelta(weeks=week_index)


def draw_feedback(rng: random.Random, weights: dict[SetFeedback, float]) -> SetFeedback:
    options = list(weights.keys())
    probs = list(weights.values())
    return rng.choices(options, weights=probs, k=1)[0]


# Per feedback-mode weighted distributions. "burst" is deliberately designed
# so a session drawing from it clears both classify_session thresholds
# (hard+max >= 50%, or max alone >= 25%) most of the time.
FEEDBACK_PROFILES: dict[str, dict[SetFeedback, float]] = {
    "benign": {SetFeedback.EASY: 0.2, SetFeedback.NORMAL: 0.7, SetFeedback.HARD: 0.1, SetFeedback.MAX: 0.0},
    "very_benign": {SetFeedback.EASY: 0.5, SetFeedback.NORMAL: 0.5, SetFeedback.HARD: 0.0, SetFeedback.MAX: 0.0},
    "burst": {SetFeedback.EASY: 0.0, SetFeedback.NORMAL: 0.1, SetFeedback.HARD: 0.55, SetFeedback.MAX: 0.35},
}


# ---- outbox dispatch (real handler functions, no RabbitMQ hop) ----


async def dispatch_pending_outbox_events(session) -> None:
    result = await session.execute(
        select(OutboxEvent).where(OutboxEvent.published_at.is_(None)).order_by(OutboxEvent.created_at)
    )
    events = result.scalars().all()
    for event in events:
        if event.event_type == EVENT_TYPE:
            for handler in get_handlers(EVENT_TYPE):
                await handler(event.payload, event.id)
        event.published_at = datetime.now(timezone.utc)
    if events:
        await session.commit()


# ---- overload diagnostics (read-only re-derivation, for per-session report granularity) ----


async def overload_diagnostics(session, user_id: uuid.UUID):
    overload_repo = OverloadRepository(session)
    recent = await overload_repo.list_recent_session_feedback_counts(
        user_id, limit=max(TACTICAL_BRAKE_WINDOW, STRUCTURAL_REPLAY_LOOKBACK)
    )
    signals_newest_first = [
        s
        for s in (classify_session(hard_count=h, max_count=m, total_with_feedback=t) for h, m, t in recent)
        if s is not None
    ]
    tactical = tactical_brake_engaged(signals_newest_first)
    throttle = compute_difficulty_throttle_steps(list(reversed(signals_newest_first)))
    return tactical, throttle


# ---- per-day / per-week orchestration ----


async def run_training_day(
    session,
    user: User,
    training_session: TrainingSession,
    feedback_weights: dict[SetFeedback, float],
    rng: random.Random,
    report: ScenarioReport,
) -> dict:
    """Logs sets/feedback for every block whose exercise has target_sets
    (matching what the real SetLogger UI would ever show), completes every
    block (matching the manual-checkbox fallback for exercises with no
    target_sets), and dispatches the resulting block_completed events for
    real. Returns feedback counts used, for the report.
    """
    result = await session.execute(
        select(SessionBlock)
        .where(SessionBlock.session_id == training_session.id)
        .options(selectinload(SessionBlock.exercise))
        .order_by(SessionBlock.order)
    )
    blocks = result.scalars().all()

    set_service = SetCompletionService(session)
    block_service = SessionBlockService(session)
    weight_service = WeightSuggestionService(session)
    reps_service = RepsSuggestionService(session)

    feedback_counts: dict[str, int] = defaultdict(int)

    for block in blocks:
        exercise = block.exercise
        if exercise.target_sets is not None:
            weight_kg = None
            if exercise.tracks_weight:
                weight_kg = await weight_service.suggest_weight(user, exercise)
                if weight_kg is None:
                    weight_kg = 20.0  # catalog gap fallback (no bodyweight_ratio yet) -- never 0/None
            # Same single-fetch-reused-across-the-session's-sets shape as
            # weight_kg above (Phase: П.1 double progression) -- reps is a
            # [rep_range_min, rep_range_max] range now, not a static
            # exercise.target_reps.
            reps_completed = await reps_service.suggest_reps(user, exercise)
            if reps_completed is None:
                reps_completed = 10  # catalog gap fallback (no rep range yet) -- never 0/None
            for set_number in range(1, exercise.target_sets + 1):
                await set_service.save_set(
                    user=user,
                    exercise_id=exercise.id,
                    training_session_id=training_session.id,
                    set_number=set_number,
                    weight_kg=weight_kg,
                    reps_completed=reps_completed,
                    duration_seconds_completed=None,
                )
            feedback = draw_feedback(rng, feedback_weights)
            await set_service.save_feedback(
                user=user,
                exercise_id=exercise.id,
                training_session_id=training_session.id,
                feedback=feedback,
            )
            feedback_counts[feedback.value] += 1

        await block_service.complete_block(block.id, user)
        await dispatch_pending_outbox_events(session)

    return feedback_counts


async def run_week(
    session,
    user: User,
    week_index: int,
    start_monday: date,
    day_pattern: dict[int, DaySessionType],
    feedback_mode_for_week: str,
    rng: random.Random,
    report: ScenarioReport,
    session_ordinal_start: int,
    previous_block_state: tuple | None,
) -> tuple:
    """Returns (updated session_ordinal, new_block_state) -- new_block_state
    is (block_number, phase.value), compared by the caller against what it
    was BEFORE this call (i.e. as of the end of the previous week's
    processing) to detect a transition. resolve_active_block/
    get_or_create_and_resolve are each a single idempotent catch-up call,
    not a "before" vs "after" pair within one call -- the only way to see
    "did this week's resolution move anything" is to compare against state
    carried in from the previous iteration.
    """
    training_block_service = TrainingBlockService(session)
    overload_service = OverloadService(session)
    schedule_service = ScheduleService(session)
    schedule_repo = ScheduleRepository(session)

    monday = week_monday(start_monday, week_index)

    resolve_t0 = time.perf_counter()
    block = await training_block_service.get_or_create_and_resolve(user.id, today=monday)
    new_block_state = (block.block_number, block.phase.value)
    block_phase = await overload_service.apply_brakes(user, block.phase)
    resolve_seconds = time.perf_counter() - resolve_t0

    weekly_plan = WeeklyPlan(user_id=user.id, week_start_date=monday, training_block_id=block.id)
    day_entries = []
    assembly_t0 = time.perf_counter()
    for offset in range(7):
        day_date = monday + timedelta(days=offset)
        session_type = day_pattern.get(offset, DaySessionType.REST)
        day_plan = DayPlan(
            date=day_date,
            session_type=session_type,
            on_ice_minutes=60 if session_type == DaySessionType.ON_ICE else None,
        )
        if session_type != DaySessionType.REST:
            day_plan.training_session = await schedule_service._build_training_session(
                session_type, user, block_phase
            )
        weekly_plan.day_plans.append(day_plan)
        day_entries.append((day_date, day_plan, session_type))
    assembly_seconds = time.perf_counter() - assembly_t0

    await schedule_repo.save(weekly_plan)
    await session.commit()

    if previous_block_state is not None and previous_block_state != new_block_state:
        report.phase_transitions.append(
            PhaseTransition(
                session_ordinal=session_ordinal_start,
                week_index=week_index,
                week_monday=monday,
                from_block=previous_block_state,
                to_block=new_block_state,
            )
        )

    prev_tactical, prev_throttle = await overload_diagnostics(session, user.id)

    session_ordinal = session_ordinal_start
    for day_date, day_plan, session_type in day_entries:
        if session_type == DaySessionType.REST or day_plan.training_session is None:
            continue
        session_ordinal += 1
        try:
            feedback_counts = await run_training_day(
                session, user, day_plan.training_session, FEEDBACK_PROFILES[feedback_mode_for_week], rng, report
            )
        except Exception as exc:  # noqa: BLE001 -- must not abort the whole scenario
            report.exceptions.append(
                {
                    "session_ordinal": session_ordinal,
                    "week_index": week_index,
                    "day_date": day_date.isoformat(),
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                }
            )
            continue

        await session.refresh(user)
        tactical, throttle = await overload_diagnostics(session, user.id)
        if tactical != prev_tactical:
            report.brake_events.append(
                BrakeEvent(
                    kind="tactical",
                    direction="engaged" if tactical else "released",
                    session_ordinal=session_ordinal,
                    week_index=week_index,
                    day_date=day_date,
                    detail=f"feedback this session: {dict(feedback_counts)}",
                )
            )
        if throttle != prev_throttle:
            report.brake_events.append(
                BrakeEvent(
                    kind="structural",
                    direction="push" if throttle > prev_throttle else "recover",
                    session_ordinal=session_ordinal,
                    week_index=week_index,
                    day_date=day_date,
                    detail=f"throttle {prev_throttle} -> {throttle}",
                )
            )
        prev_tactical, prev_throttle = tactical, throttle

        report.sessions.append(
            SessionRecord(
                week_index=week_index,
                session_ordinal=session_ordinal,
                day_date=day_date,
                session_type=session_type.value,
                block_phase=block_phase.value,
                feedback_mode=feedback_mode_for_week,
                feedback_counts=dict(feedback_counts),
                level_after=user.level,
                xp_after=user.xp,
                tactical_brake_after=tactical,
                structural_throttle_after=throttle,
            )
        )
        report.total_sessions_completed += 1

    report.timing_samples.append(
        TimingSample(session_ordinal=session_ordinal, resolve_seconds=resolve_seconds, assembly_seconds=assembly_seconds)
    )

    if week_index % 4 == 0:
        report.level_checkpoints.append(
            LevelCheckpoint(
                week_index=week_index, level=user.level, xp=user.xp, max_difficulty=max_difficulty_for_level(user.level)
            )
        )

    return session_ordinal, new_block_state


# ---- scenario definitions ----


def scenario_1_pattern(week_index: int) -> tuple[dict[int, DaySessionType], str]:
    return _SESSION_TYPE_CATEGORY_DAYS, "benign"


def scenario_2_pattern(week_index: int) -> tuple[dict[int, DaySessionType], str]:
    # 4 busy weeks / 3 ordinary-gap weeks, repeating, with one deliberately
    # long (9-week) gap inserted to exceed PHASE_CALENDAR_CEILING_WEEKS=8 and
    # prove the soft ceiling actually fires, not just "phase never advances
    # on empty weeks" (the easy half of the expectation).
    busy_blocks = [range(0, 4), range(8, 12), range(21, 25)]
    is_busy = any(week_index in block for block in busy_blocks)
    pattern = _SESSION_TYPE_CATEGORY_DAYS if is_busy else {}
    return pattern, "benign"


def scenario_3_pattern(week_index: int) -> tuple[dict[int, DaySessionType], str]:
    # 8-session repeating cycle: 2 overload sessions back-to-back (trips the
    # tactical brake), a breather, a lone overload, then 3 clean sessions --
    # designed to hit both brakes multiple times without being permanently
    # maxed out (a stuck-forever throttle would say nothing about recovery).
    cycle = ["burst", "burst", "benign", "burst", "benign", "benign", "benign", "benign"]
    week_mode = cycle[week_index % len(cycle)]
    return _SESSION_TYPE_CATEGORY_DAYS, week_mode


def scenario_4_pattern(week_index: int) -> tuple[dict[int, DaySessionType], str]:
    return _SESSION_TYPE_CATEGORY_DAYS, "very_benign"


SCENARIOS = [
    ("stable", "3x/неделю, 26 недель, благоприятный feedback -- без сбоев", scenario_1_pattern, 1001),
    ("irregular", "Переменная частота (густо/пусто), включая гэп > 8 недель", scenario_2_pattern, 1002),
    ("overloaded", "3x/неделю, спроектированные всплески hard/max для обоих тормозов", scenario_3_pattern, 1003),
    ("fast_progress", "3x/неделю, преимущественно easy/normal -- кривая level", scenario_4_pattern, 1004),
]


# ---- scenario runner ----


async def run_scenario(tag: str, description: str, pattern_fn, seed: int) -> ScenarioReport:
    report = ScenarioReport(name=tag, description=description)
    rng = random.Random(seed)
    random.seed(seed)  # ScheduleService's own random.randint/choice picks -- reproducible, not frozen

    start_wall = time.perf_counter()
    start_monday = date(2025, 1, 6)  # a Monday; simulated, not real "today"

    async with AsyncSessionLocal() as session:
        user = await make_test_user(session, tag)
        await session.commit()
        report.user_id = user.id

        session_ordinal = 0
        block_state = None
        for week_index in range(WEEKS):
            day_pattern, feedback_mode = pattern_fn(week_index)
            print(f"[{tag}] week {week_index + 1}/{WEEKS} (sessions so far: {session_ordinal})", flush=True)
            session_ordinal, block_state = await run_week(
                session,
                user,
                week_index,
                start_monday,
                day_pattern,
                feedback_mode,
                rng,
                report,
                session_ordinal,
                block_state,
            )

        stat_rows = await session.execute(
            select(StatHistory.stat_type, func.count(), func.sum(StatHistory.value))
            .where(StatHistory.user_id == user.id)
            .group_by(StatHistory.stat_type)
        )
        report.stat_distribution = {
            row[0].value: {"count": row[1], "total_gain": round(float(row[2]), 2)} for row in stat_rows.all()
        }

    report.wall_clock_seconds = time.perf_counter() - start_wall
    return report


# ---- report rendering ----


def _fmt_seconds(value: float) -> str:
    return f"{value:.3f}s"


def render_report(reports: list[ScenarioReport]) -> str:
    lines = ["# IceLevel -- долгосрочная симуляция (26 недель), отчёт", ""]
    lines.append(f"Сгенерировано: {datetime.now(timezone.utc).isoformat()}Z")
    lines.append("")

    for report in reports:
        lines.append(f"## Сценарий: {report.name}")
        lines.append(f"{report.description}")
        lines.append("")
        lines.append(f"- Тестовый пользователь: `{report.user_id}`")
        lines.append(f"- Всего завершённых сессий: {report.total_sessions_completed}")
        lines.append(f"- Время выполнения сценария: {_fmt_seconds(report.wall_clock_seconds)}")
        lines.append("")

        lines.append("### 1. Таймлайн переходов block_phase")
        if not report.phase_transitions:
            lines.append("Переходов не зафиксировано.")
        else:
            lines.append("| Сессия # | Неделя | Дата (пн) | Было | Стало |")
            lines.append("|---|---|---|---|---|")
            for t in report.phase_transitions:
                lines.append(
                    f"| {t.session_ordinal} | {t.week_index + 1} | {t.week_monday.isoformat()} | "
                    f"block {t.from_block[0]}/{t.from_block[1]} | block {t.to_block[0]}/{t.to_block[1]} |"
                )
        lines.append("")

        lines.append("### 2. Кривая level/xp (контрольные точки каждые 4 недели)")
        lines.append("| Неделя | level | xp | макс. доступная сложность |")
        lines.append("|---|---|---|---|")
        for c in report.level_checkpoints:
            lines.append(f"| {c.week_index + 1} | {c.level} | {c.xp} | {c.max_difficulty} |")
        lines.append("")

        lines.append("### 3. Срабатывания тормозов")
        if not report.brake_events:
            lines.append("Ни один тормоз не сработал.")
        else:
            lines.append("| Сессия # | Неделя | Дата | Тормоз | Событие | Детали |")
            lines.append("|---|---|---|---|---|---|")
            for b in report.brake_events:
                lines.append(
                    f"| {b.session_ordinal} | {b.week_index + 1} | {b.day_date.isoformat()} | "
                    f"{b.kind} | {b.direction} | {b.detail} |"
                )
        lines.append("")

        lines.append("### 4. Распределение наград по target_stat")
        if not report.stat_distribution:
            lines.append("Нет данных (ни одного начисления).")
        else:
            lines.append("| Stat | Кол-во начислений | Суммарный прирост |")
            lines.append("|---|---|---|")
            for stat, agg in sorted(report.stat_distribution.items()):
                lines.append(f"| {stat} | {agg['count']} | {agg['total_gain']} |")
        lines.append("")

        lines.append("### 5. Исключения при накоплении истории")
        if not report.exceptions:
            lines.append("Исключений не зафиксировано.")
        else:
            for e in report.exceptions:
                lines.append(
                    f"- Сессия #{e['session_ordinal']} (неделя {e['week_index'] + 1}, {e['day_date']}): {e['error']}"
                )
                lines.append("  ```")
                lines.append("  " + e["traceback"].replace("\n", "\n  "))
                lines.append("  ```")
        lines.append("")

        lines.append("### 6. Тайминги резолва блока/сборки сессии -- первые 10 vs последние 10")
        samples = report.timing_samples
        if len(samples) >= 2:
            first10 = samples[:10]
            last10 = samples[-10:]
            avg_resolve_first = sum(s.resolve_seconds for s in first10) / len(first10)
            avg_resolve_last = sum(s.resolve_seconds for s in last10) / len(last10)
            avg_assembly_first = sum(s.assembly_seconds for s in first10) / len(first10)
            avg_assembly_last = sum(s.assembly_seconds for s in last10) / len(last10)
            lines.append(
                f"- resolve (block/overload): первые {_fmt_seconds(avg_resolve_first)} -> "
                f"последние {_fmt_seconds(avg_resolve_last)}"
            )
            lines.append(
                f"- assembly (сборка недели): первые {_fmt_seconds(avg_assembly_first)} -> "
                f"последние {_fmt_seconds(avg_assembly_last)}"
            )
        else:
            lines.append("Недостаточно данных для сравнения.")
        lines.append("")

    return "\n".join(lines)


async def main() -> None:
    reports = []
    for tag, description, pattern_fn, seed in SCENARIOS:
        print(f"=== starting scenario: {tag} ===", flush=True)
        report = await run_scenario(tag, description, pattern_fn, seed)
        reports.append(report)
        print(
            f"=== finished scenario: {tag} in {_fmt_seconds(report.wall_clock_seconds)}, "
            f"{report.total_sessions_completed} sessions, {len(report.exceptions)} exceptions ===",
            flush=True,
        )

    report_text = render_report(reports)
    REPORT_PATH.write_text(report_text, encoding="utf-8")
    print(f"\nReport written to {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
