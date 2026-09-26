"""A year (52 weeks) of use for seven kinds of player, run against the REAL
service layer -- builds on scripts/simulate_long_term_usage.py (same week
assembly, periodization, overload brakes, set logging and block_completed
handlers; read its docstring for how simulated time works) and adds what a
year shows that half a year doesn't:

- season periods switching over the year and a tournament taper;
- a home player without a gym, a 5x/week player, a 2x/week beginner, a
  long summer break;
- exercise variety (unique exercises per quarter, the same exercise in
  back-to-back sessions), session size, weight progression;
- warnings logged by the picker (archetype/pool fallbacks);
- the Analytics overview computed on the whole year.

The year ends last Sunday, so the Analytics overview (which works from the
real "today") sees it as recent history. Set and block completion times are
moved onto their simulated day after the run for the same reason.

    docker compose exec backend python scripts/simulate_year.py

Writes scripts/simulation_year_report.md.
"""
import asyncio
import logging
import random
import sys
import time
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.core.training_block import is_tapering  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import TrainingPhase  # noqa: E402
from app.models.progress import UserStat  # noqa: E402
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan  # noqa: E402
from app.models.set_completion import SetCompletion  # noqa: E402
from app.models.user import SeasonPeriod, User  # noqa: E402
from app.services.analytics_overview_service import AnalyticsOverviewService  # noqa: E402

from simulate_long_term_usage import ScenarioReport, make_test_user, run_week  # noqa: E402

WEEKS = 52
REPORT_PATH = Path(__file__).resolve().parent / "simulation_year_report.md"

OFF, ON = DaySessionType.OFF_ICE, DaySessionType.ON_ICE
THREE_A_WEEK = {0: OFF, 2: OFF, 4: ON}
FIVE_A_WEEK = {0: OFF, 1: OFF, 2: ON, 3: OFF, 5: OFF}
TWO_A_WEEK = {1: OFF, 4: OFF}
HOME_WEEK = {0: OFF, 2: OFF, 4: OFF}


def season_for(week: int) -> SeasonPeriod:
    """A hockey year from January: season, playoffs, summer offseason,
    preseason camp, season again."""
    if week < 12:
        return SeasonPeriod.SEASON
    if week < 18:
        return SeasonPeriod.PLAYOFFS
    if week < 32:
        return SeasonPeriod.OFFSEASON
    if week < 38:
        return SeasonPeriod.PRESEASON
    return SeasonPeriod.SEASON


@dataclass
class Scenario:
    tag: str
    description: str
    seed: int
    days: dict = field(default_factory=lambda: THREE_A_WEEK)
    feedback: str = "benign"
    has_gym: bool = True
    age: int = 20
    # week -> False to skip the whole week
    active: callable = lambda week: True
    feedback_for: callable = None
    tournaments: tuple = ()  # week indexes; the tournament is that week's Saturday
    seasons: bool = True


BURST_CYCLE = ["burst", "burst", "benign", "burst", "benign", "benign", "benign", "benign"]

SCENARIOS = [
    Scenario("stable", "3 раза в неделю весь год (2 зала + лёд), обычные ощущения, сезоны меняются", 2001),
    Scenario(
        "intense",
        "5 раз в неделю (4 зала + лёд), иногда тяжело",
        2002,
        days=FIVE_A_WEEK,
        feedback_for=lambda week: "burst" if week % 6 == 5 else "benign",
    ),
    Scenario(
        "summer_break",
        "3 раза в неделю, летний перерыв 10 недель и редкие недели в межсезонье",
        2003,
        active=lambda week: not (20 <= week < 30) and not (30 <= week < 36 and week % 2 == 1),
    ),
    Scenario("overloaded", "3 раза в неделю, регулярные всплески «тяжело/максимум»", 2004, feedback_for=lambda week: BURST_CYCLE[week % 8]),
    Scenario("home_no_gym", "3 раза в неделю дома, без зала", 2005, days=HOME_WEEK, has_gym=False),
    Scenario("tournaments", "3 раза в неделю, два турнира (неделя 16 и 44) — подводка", 2006, tournaments=(16, 44)),
    Scenario("beginner_2x", "Новичок 14 лет, 2 раза в неделю, всё легко", 2007, days=TWO_A_WEEK, feedback="very_benign", age=14),
]


class WarningCounter(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.counts: Counter = Counter()

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        self.counts[f"{record.name}: {message.split(':')[0][:90]}"] += 1


@dataclass
class YearResult:
    scenario: Scenario
    report: ScenarioReport
    seconds: float = 0.0
    warnings: Counter = field(default_factory=Counter)
    phase_weeks: Counter = field(default_factory=Counter)
    main_counts: list = field(default_factory=list)
    main_counts_taper: list = field(default_factory=list)
    empty_off_ice: int = 0
    unique_by_quarter: list = field(default_factory=list)
    repeat_rate: float = 0.0
    top_exercises: list = field(default_factory=list)
    weight_track: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    level: int = 0
    overview: dict = field(default_factory=dict)
    overview_errors: list = field(default_factory=list)


async def run_year(scenario: Scenario, start_monday: date, warnings: WarningCounter) -> YearResult:
    report = ScenarioReport(name=scenario.tag, description=scenario.description)
    result = YearResult(scenario=scenario, report=report)
    rng = random.Random(scenario.seed)
    random.seed(scenario.seed)
    warnings.counts = Counter()
    started = time.perf_counter()

    async with AsyncSessionLocal() as session:
        user = await make_test_user(session, scenario.tag)
        user.has_gym_access = scenario.has_gym
        user.age = scenario.age
        user.timezone = "UTC"
        user.has_premium = True
        await session.commit()
        report.user_id = user.id

        ordinal, block_state = 0, None
        for week in range(WEEKS):
            monday = start_monday + timedelta(weeks=week)
            if scenario.seasons:
                user.season_period = season_for(week)
            upcoming = [t for t in scenario.tournaments if t >= week]
            user.tournament_date = (start_monday + timedelta(weeks=upcoming[0], days=5)) if upcoming else None
            await session.commit()

            days = scenario.days if scenario.active(week) else {}
            feedback = scenario.feedback_for(week) if scenario.feedback_for else scenario.feedback
            print(f"[{scenario.tag}] week {week + 1}/{WEEKS} (sessions: {ordinal})", flush=True)
            try:
                ordinal, block_state = await run_week(
                    session, user, week, start_monday, days, feedback, rng, report, ordinal, block_state
                )
            except Exception as exc:  # noqa: BLE001 -- keep going, report it
                await session.rollback()
                report.exceptions.append(
                    {
                        "session_ordinal": ordinal,
                        "week_index": week,
                        "day_date": monday.isoformat(),
                        "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(),
                    }
                )
            for record in report.sessions:
                if record.week_index == week and record.session_type == OFF.value:
                    result.phase_weeks[record.block_phase] += 1
                    break

        await backdate_completions(session, user)
        await collect(session, user, result, start_monday)
        await analytics(session, user, result)

    result.seconds = time.perf_counter() - started
    result.warnings = Counter(warnings.counts)
    return result


async def backdate_completions(session, user: User) -> None:
    """Completion times onto the simulated day (18:00 UTC), so analytics
    sees the year as it happened instead of all of it "today"."""
    await session.execute(
        text(
            """
            UPDATE session_blocks sb SET completed_at = dp.date + time '18:00'
            FROM training_sessions ts JOIN day_plans dp ON dp.id = ts.day_plan_id
            JOIN weekly_plans wp ON wp.id = dp.weekly_plan_id
            WHERE sb.session_id = ts.id AND wp.user_id = :user_id AND sb.completed_at IS NOT NULL
            """
        ),
        {"user_id": user.id},
    )
    await session.execute(
        text(
            """
            UPDATE set_completions sc SET completed_at = dp.date + time '18:00' + (sc.set_number * interval '3 minutes')
            FROM training_sessions ts JOIN day_plans dp ON dp.id = ts.day_plan_id
            WHERE sc.training_session_id = ts.id AND sc.user_id = :user_id
            """
        ),
        {"user_id": user.id},
    )
    await session.commit()


async def collect(session, user: User, result: YearResult, start_monday: date) -> None:
    plans = (
        await session.scalars(
            select(DayPlan)
            .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
            .where(WeeklyPlan.user_id == user.id)
            .options(
                selectinload(DayPlan.training_session)
                .selectinload(TrainingSession.blocks)
                .selectinload(SessionBlock.exercise)
            )
            .order_by(DayPlan.date)
        )
    ).all()

    previous_main: set = set()
    repeats = total = 0
    by_quarter: dict[int, set] = defaultdict(set)
    counter: Counter = Counter()
    for plan in plans:
        if plan.session_type != OFF or plan.training_session is None:
            continue
        main = [block.exercise for block in plan.training_session.blocks if block.phase == TrainingPhase.MAIN]
        count = len(main)
        tapering = is_tapering(plan.date, next((t for t in _tournament_dates(result.scenario, start_monday) if t >= plan.date), None))
        (result.main_counts_taper if tapering else result.main_counts).append(count)
        if count == 0:
            result.empty_off_ice += 1
        names = {exercise.name for exercise in main}
        repeats += len(names & previous_main)
        total += len(names)
        previous_main = names
        quarter = (plan.date - start_monday).days // 91
        by_quarter[quarter] |= names
        counter.update(names)
    result.unique_by_quarter = [len(by_quarter[q]) for q in range(4)]
    result.repeat_rate = repeats / total if total else 0.0
    result.top_exercises = counter.most_common(5)

    # Weight over the year for the most-logged weighted exercise.
    sets = (
        await session.scalars(
            select(SetCompletion)
            .where(SetCompletion.user_id == user.id, SetCompletion.weight_kg.is_not(None))
            .order_by(SetCompletion.completed_at)
        )
    ).all()
    by_exercise: dict = defaultdict(list)
    for entry in sets:
        by_exercise[entry.exercise_id].append(entry)
    if by_exercise:
        exercise_id, entries = max(by_exercise.items(), key=lambda item: len(item[1]))
        name = next(
            (b.exercise.name for p in plans if p.training_session for b in p.training_session.blocks if b.exercise_id == exercise_id),
            str(exercise_id),
        )
        per_session: dict = {}
        for entry in entries:
            per_session.setdefault(entry.training_session_id, (entry.completed_at.date(), entry.weight_kg, entry.reps_completed))
        track = list(per_session.values())
        picks = sorted({0, len(track) // 4, len(track) // 2, 3 * len(track) // 4, len(track) - 1})
        result.weight_track = [(name, len(track))] + [track[i] for i in picks]

    stats = (await session.scalars(select(UserStat).where(UserStat.user_id == user.id))).all()
    result.stats = {stat.stat_type.value: round(stat.current_value, 1) for stat in stats}
    await session.refresh(user)
    result.level = user.level


def _tournament_dates(scenario: Scenario, start_monday: date) -> list[date]:
    return [start_monday + timedelta(weeks=t, days=5) for t in scenario.tournaments]


async def analytics(session, user: User, result: YearResult) -> None:
    service = AnalyticsOverviewService(session)
    for days in (30, 90, 365):
        try:
            started = time.perf_counter()
            overview = await service.get_overview(user, days)
            result.overview[days] = {
                "seconds": time.perf_counter() - started,
                "insights": [f"{i.title} — {i.detail}" for i in overview.insights],
                "records": len(overview.records),
                "top_record": (
                    f"{overview.records[0].exercise_name}: {overview.records[0].before} → {overview.records[0].after} {overview.records[0].unit}"
                    if overview.records
                    else None
                ),
                "regularity": f"{overview.regularity.completed_sessions}/{overview.regularity.planned_sessions}, серия {overview.regularity.streak_days}",
                "most_skipped": [f"{s.exercise_name} ×{s.count}" for s in overview.regularity.most_skipped],
                "load": [(w.week_start.isoformat(), w.tonnage_kg, w.sets, w.hard_share) for w in overview.load.weeks],
                "load_warning": overview.load.warning,
                "balance": {g.group: round(g.share * 100) for g in overview.balance.groups},
                "balance_note": overview.balance.note,
            }
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            result.overview_errors.append(f"days={days}: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")


def render(results: list[YearResult], start_monday: date) -> str:
    out = [
        "# IceLevel — симуляция на год (52 недели), отчёт",
        "",
        f"Сгенерировано: {datetime.now(timezone.utc).isoformat()}",
        f"Год симуляции: {start_monday.isoformat()} — {(start_monday + timedelta(weeks=WEEKS, days=-1)).isoformat()}",
        "",
        "## Сводка",
        "",
        "| Сценарий | Сессий | Исключений | Уровень | Пустых зал-сессий | Упражнений в зал-сессии (ср.) | Повтор подряд | Уникальных по кварталам | Время |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        avg_main = f"{mean(r.main_counts):.1f}" if r.main_counts else "—"
        out.append(
            f"| {r.scenario.tag} | {r.report.total_sessions_completed} | {len(r.report.exceptions) + len(r.overview_errors)} | {r.level} | "
            f"{r.empty_off_ice} | {avg_main} | {r.repeat_rate:.0%} | {' / '.join(map(str, r.unique_by_quarter))} | {r.seconds:.0f} с |"
        )
    out.append("")

    for r in results:
        rep = r.report
        out += [f"## {r.scenario.tag}", r.scenario.description, "", f"- Пользователь: `{rep.user_id}`"]
        out.append(f"- Фазы (недель с зал-сессиями): {dict(r.phase_weeks)}")
        out.append(f"- Переходов блоков: {len(rep.phase_transitions)}; последний: " + (
            f"block {rep.phase_transitions[-1].to_block[0]}/{rep.phase_transitions[-1].to_block[1]} (неделя {rep.phase_transitions[-1].week_index + 1})"
            if rep.phase_transitions else "—"
        ))
        tactical = sum(1 for b in rep.brake_events if b.kind == "tactical" and b.direction == "engaged")
        structural = sum(1 for b in rep.brake_events if b.kind == "structural" and b.direction == "push")
        out.append(f"- Тормоза: тактический включался {tactical} раз, структурный дожимал {structural} раз")
        if r.main_counts_taper:
            out.append(
                f"- Подводка к турниру: упражнений в зал-сессии {mean(r.main_counts_taper):.1f} против {mean(r.main_counts):.1f} в обычные недели"
            )
        if r.main_counts:
            out.append(f"- Упражнений основной части: мин {min(r.main_counts)}, макс {max(r.main_counts)}")
        out.append(f"- Самые частые упражнения: " + ", ".join(f"{name} ×{count}" for name, count in r.top_exercises))
        if r.weight_track:
            (name, sessions), *points = r.weight_track
            out.append(f"- Вес по году, «{name}» ({sessions} сессий): " + " → ".join(f"{d.isoformat()} {w} кг×{reps}" for d, w, reps in points))
        out.append(f"- Характеристики в конце года: {r.stats}")
        if r.warnings:
            out.append("- Предупреждения подбора:")
            for message, count in r.warnings.most_common(8):
                out.append(f"  - {count}× {message}")
        else:
            out.append("- Предупреждений подбора нет")
        for days, data in r.overview.items():
            out.append(f"- Аналитика за {days} дн. ({data['seconds']:.2f} с):")
            for insight in data["insights"]:
                out.append(f"  - вывод: {insight}")
            out.append(f"  - рекордов {data['records']}" + (f", лучший: {data['top_record']}" if data["top_record"] else ""))
            out.append(f"  - регулярность {data['regularity']}; пропускает: {data['most_skipped'] or '—'}")
            out.append(f"  - нагрузка по неделям: {data['load']}; предупреждение: {data['load_warning'] or '—'}")
            out.append(f"  - баланс: {data['balance']}; заметка: {data['balance_note'] or '—'}")
        for error in r.overview_errors:
            out += ["- ОШИБКА аналитики:", "  ```", "  " + error.replace("\n", "\n  "), "  ```"]
        for e in rep.exceptions:
            out += [f"- ИСКЛЮЧЕНИЕ, неделя {e['week_index'] + 1} ({e['day_date']}): {e['error']}", "  ```", "  " + e["traceback"].replace("\n", "\n  "), "  ```"]
        out.append("")
    return "\n".join(out)


async def main() -> None:
    today = datetime.now(timezone.utc).date()
    this_monday = today - timedelta(days=today.weekday())
    start_monday = this_monday - timedelta(weeks=WEEKS)
    warnings = WarningCounter()
    logging.getLogger().addHandler(warnings)
    only = set(sys.argv[1:])
    results = []
    for scenario in SCENARIOS:
        if only and scenario.tag not in only:
            continue
        print(f"=== {scenario.tag} ===", flush=True)
        result = await run_year(scenario, start_monday, warnings)
        results.append(result)
        print(
            f"=== {scenario.tag}: {result.report.total_sessions_completed} sessions, "
            f"{len(result.report.exceptions)} exceptions, {len(result.overview_errors)} analytics errors, {result.seconds:.0f}s ===",
            flush=True,
        )
    REPORT_PATH.write_text(render(results, start_monday), encoding="utf-8")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
