"""How often each catalog exercise actually lands in plans, across very
different players -- the input for "which exercises to film first"
(2026-10-03). Runs the REAL week assembly (same path as
ScheduleService.create_weekly_plan: training block + brakes, archetype
round-robin, guaranteed endurance/locomotion days, team-day dispatch) and
the real set logging / block_completed handlers from
simulate_long_term_usage.py, so stats grow, pins form and rotate, blocks
advance, exactly as for a real player.

Each scenario differs in what the picker actually reads: equipment owned,
gym access, starting stats and level (difficulty gate), session mix (off-ice
/ on-ice / game days), season period, tournament taper, temporary
restrictions, skill preferences and feedback (overload brakes). Age and
position are not read by the picker, so they don't vary.

Run against a COPY of the catalog, never prod (it creates users and plans):

    docker compose exec -e DATABASE_URL=...hlu_freq backend \\
        python scripts/simulate_exercise_frequency.py out.json [weeks]

Writes a JSON with per-exercise counts (total, per scenario, per phase) and
the scenario list.
"""
import asyncio
import json
import random
import sys
import time
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import (  # noqa: E402
    EquipmentItem,
    Exercise,
    ExerciseCategory,
    MovementPattern,
    MuscleGroup,
    TargetStat,
    UserEquipmentItem,
)
from app.models.progress import UserStat  # noqa: E402
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan  # noqa: E402
from app.models.skill import Skill, UserSkillPreference  # noqa: E402
from app.models.user import SeasonPeriod  # noqa: E402
from app.models.user_temporary_restriction import UserTemporaryRestriction  # noqa: E402
from app.repositories.schedule_repository import ScheduleRepository  # noqa: E402
from app.schemas.schedule import DayPlanIn  # noqa: E402
from app.services.overload_service import OverloadService  # noqa: E402
from app.services.schedule_service import ScheduleService  # noqa: E402
from app.services.training_block_service import TrainingBlockService  # noqa: E402

from simulate_long_term_usage import (  # noqa: E402
    FEEDBACK_PROFILES,
    ScenarioReport,
    make_test_user,
    run_training_day,
)

OFF, ON, GAME = DaySessionType.OFF_ICE, DaySessionType.ON_ICE, DaySessionType.GAME
E = EquipmentItem
HOME_BASIC = [E.RESISTANCE_BAND, E.JUMP_ROPE, E.FOAM_ROLLER]
HOME_FULL = [E.DUMBBELLS, E.KETTLEBELL, E.RESISTANCE_BAND, E.PULL_UP_BAR, E.STEP_PLATFORM, E.MEDICINE_BALL,
             E.FOAM_ROLLER, E.JUMP_ROPE, E.FITBALL, E.SLIDE_BOARD]


@dataclass
class Scenario:
    tag: str
    description: str
    seed: int
    days: dict  # weekday -> session type
    has_gym: bool = True
    equipment: list = field(default_factory=list)
    stats: float = 0.0  # starting value of every stat (0 = brand new player)
    level: int = 1
    season: SeasonPeriod | None = None  # None = season all along
    tournaments: tuple = ()  # week indexes (Saturday of that week)
    feedback: str = "benign"
    burst_every: int = 0  # every Nth week "burst" feedback
    restrict_patterns: tuple = ()
    restrict_muscles: tuple = ()
    skill_prefs: int = 0  # how many skills to prefer (picked at random)


SCENARIOS = [
    Scenario("novice_home_nothing", "Новичок дома, без инвентаря, 2 раза в неделю, всё легко", 31,
             {1: OFF, 4: OFF}, has_gym=False, feedback="very_benign"),
    Scenario("home_bands", "Дома: резина, скакалка, ролл; 3 зала в неделю", 32,
             {0: OFF, 2: OFF, 4: OFF}, has_gym=False, equipment=HOME_BASIC),
    Scenario("home_full_stick", "Дома всё (гантели, гири, турник, тумба, медбол...) + клюшка; 3 зала + лёд", 33,
             {0: OFF, 2: OFF, 3: ON, 5: OFF}, has_gym=False, equipment=HOME_FULL + [E.HOCKEY_STICK]),
    Scenario("puck_home", "Дома только клюшка и резина, 4 зала в неделю", 34,
             {0: OFF, 1: OFF, 3: OFF, 5: OFF}, has_gym=False, equipment=[E.HOCKEY_STICK, E.RESISTANCE_BAND]),
    Scenario("gym_standard", "Зал, 2 зала + лёд, обычные ощущения", 35, {0: OFF, 2: ON, 4: OFF}),
    Scenario("gym_intense", "Зал + клюшка + сани, 5 раз в неделю, тяжёлая неделя каждые 6", 36,
             {0: OFF, 1: OFF, 2: ON, 3: OFF, 5: OFF}, equipment=[E.HOCKEY_STICK, E.SLED], burst_every=6),
    Scenario("mid_stats", "Средний уровень (статы ~45, уровень 10), зал, 3 зала", 37,
             {0: OFF, 2: OFF, 4: OFF}, stats=45, level=10, equipment=[E.HOCKEY_STICK]),
    Scenario("advanced", "Продвинутый (статы ~75, уровень 20), зал, 4 зала + лёд", 38,
             {0: OFF, 1: OFF, 3: OFF, 4: ON, 5: OFF}, stats=75, level=20, equipment=[E.HOCKEY_STICK]),
    Scenario("elite", "Топ (статы ~90, уровень 30), зал + клюшка + сани, 4 зала", 39,
             {0: OFF, 1: OFF, 3: OFF, 5: OFF}, stats=90, level=30, equipment=[E.HOCKEY_STICK, E.SLED]),
    Scenario("team_ice_heavy", "Командный: 3 льда + игра + 1 зал", 40,
             {0: ON, 1: OFF, 2: ON, 4: ON, 5: GAME}, stats=30, level=8),
    Scenario("game_weekends", "2 зала + игра каждую субботу", 41, {1: OFF, 3: OFF, 5: GAME}, stats=25, level=5),
    Scenario("knee_injury", "Травма колена: без приседа и квадрицепса весь период, зал", 42,
             {0: OFF, 2: OFF, 4: OFF}, restrict_patterns=(MovementPattern.SQUAT,),
             restrict_muscles=(MuscleGroup.QUADS,)),
    Scenario("shoulder_back", "Плечо и спина: без жима, плеч и спины, зал", 43,
             {0: OFF, 2: OFF, 4: OFF}, restrict_patterns=(MovementPattern.PUSH,),
             restrict_muscles=(MuscleGroup.SHOULDERS, MuscleGroup.BACK)),
    Scenario("tournaments", "Два турнира (недели 8 и 20) с подводкой, зал, 3 зала + лёд", 44,
             {0: OFF, 2: OFF, 3: ON, 4: OFF}, tournaments=(8, 20), stats=35, level=6),
    Scenario("offseason", "Межсезонье весь период, 4 зала, клюшка", 45,
             {0: OFF, 1: OFF, 3: OFF, 4: OFF}, season=SeasonPeriod.OFFSEASON, equipment=[E.HOCKEY_STICK],
             stats=40, level=8),
    Scenario("preseason_overloaded", "Предсезонка, постоянно тяжело/максимум", 46,
             {0: OFF, 2: OFF, 4: OFF}, season=SeasonPeriod.PRESEASON, feedback="burst", stats=30),
    Scenario("skill_focus", "Выбрал 5 любимых навыков, зал + клюшка, 3 зала", 47,
             {0: OFF, 2: OFF, 4: OFF}, equipment=[E.HOCKEY_STICK], skill_prefs=5, stats=30, level=6),
    Scenario("playoffs", "Плей-офф весь период: 2 игры + 2 льда + 1 зал", 48,
             {0: ON, 1: OFF, 2: GAME, 4: ON, 5: GAME}, season=SeasonPeriod.PLAYOFFS, stats=50, level=12),
]


async def setup_user(session, scenario: Scenario, start_monday: date):
    user = await make_test_user(session, scenario.tag)
    user.has_gym_access = scenario.has_gym
    user.level = scenario.level
    user.timezone = "UTC"
    user.has_premium = True
    if scenario.season is not None:
        user.season_period = scenario.season
    for item in scenario.equipment:
        session.add(UserEquipmentItem(user_id=user.id, equipment_item=item))
    if scenario.stats:
        for stat in TargetStat:
            session.add(UserStat(user_id=user.id, stat_type=stat, current_value=float(scenario.stats)))
    far = start_monday + timedelta(days=3650)
    for pattern in scenario.restrict_patterns:
        session.add(UserTemporaryRestriction(user_id=user.id, movement_pattern=pattern, expires_at=far))
    for muscle in scenario.restrict_muscles:
        session.add(UserTemporaryRestriction(user_id=user.id, muscle_group=muscle, expires_at=far))
    if scenario.skill_prefs:
        skills = (await session.execute(select(Skill.id))).scalars().all()
        for skill_id in random.Random(scenario.seed).sample(list(skills), min(scenario.skill_prefs, len(skills))):
            session.add(UserSkillPreference(user_id=user.id, skill_id=skill_id))
    await session.commit()
    return user


async def build_week(session, user, monday: date, days: dict):
    """create_weekly_plan's own steps, with "today" = the simulated Monday."""
    service = ScheduleService(session)
    block = await TrainingBlockService(session).get_or_create_and_resolve(user.id, today=monday)
    block_phase = await OverloadService(session).apply_brakes(user, block.phase)
    rotation = await service._build_archetype_rotation(user, ExerciseCategory.OFF_ICE)
    day_ins = [DayPlanIn(date=monday + timedelta(days=d), session_type=days.get(d, DaySessionType.REST)) for d in range(7)]
    endurance_date, locomotion_date = service._choose_guaranteed_slot_dates(day_ins)
    plan = WeeklyPlan(user_id=user.id, week_start_date=monday, training_block_id=block.id)
    sessions = []  # collected before save: relationships are not lazy-loadable afterwards
    for day_in in day_ins:
        day_plan = DayPlan(date=day_in.date, session_type=day_in.session_type)
        if day_in.session_type != DaySessionType.REST:
            day_plan.training_session = await service._build_session_for_day(
                day_in.session_type, user, block_phase, block, today=monday,
                archetype_rotation=rotation,
                guarantee_endurance=day_in.date == endurance_date,
                guarantee_locomotion=day_in.date == locomotion_date,
            )
            sessions.append(day_plan.training_session)
        plan.day_plans.append(day_plan)
    await ScheduleRepository(session).save(plan)
    await session.commit()
    return sessions


async def run_scenario(scenario: Scenario, start_monday: date, weeks: int) -> dict:
    random.seed(scenario.seed)
    rng = random.Random(scenario.seed)
    report = ScenarioReport(name=scenario.tag, description=scenario.description)
    errors = []
    async with AsyncSessionLocal() as session:
        user = await setup_user(session, scenario, start_monday)
        user_id = user.id  # attribute access after a rollback would lazy-load
        for week in range(weeks):
            monday = start_monday + timedelta(weeks=week)
            upcoming = [t for t in scenario.tournaments if t >= week]
            user.tournament_date = (start_monday + timedelta(weeks=upcoming[0], days=5)) if upcoming else None
            await session.commit()
            feedback = "burst" if scenario.burst_every and week % scenario.burst_every == scenario.burst_every - 1 \
                else scenario.feedback
            try:
                for training_session in await build_week(session, user, monday, scenario.days):
                    await run_training_day(session, user, training_session, FEEDBACK_PROFILES[feedback], rng, report)
                    await session.refresh(user)
            except Exception as exc:  # noqa: BLE001 -- keep going, report it
                await session.rollback()
                errors.append(f"week {week}: {type(exc).__name__}: {exc}\n{traceback.format_exc()[:3000]}")
            print(f"[{scenario.tag}] week {week + 1}/{weeks}", flush=True)

        rows = await session.execute(
            select(SessionBlock.exercise_id, SessionBlock.phase, DayPlan.session_type)
            .join(TrainingSession, TrainingSession.id == SessionBlock.session_id)
            .join(DayPlan, DayPlan.id == TrainingSession.day_plan_id)
            .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
            .where(WeeklyPlan.user_id == user_id)
        )
        counts = Counter()
        for exercise_id, phase, _ in rows.all():
            counts[(str(exercise_id), phase.value if hasattr(phase, "value") else str(phase))] += 1
    sessions = sum(1 for _ in scenario.days) * weeks
    return {"tag": scenario.tag, "description": scenario.description, "sessions": sessions,
            "counts": counts, "errors": errors}


async def main() -> None:
    out_path = Path(sys.argv[1])
    weeks = int(sys.argv[2]) if len(sys.argv) > 2 else 26
    only = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
    today = date.today()
    start_monday = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks)
    results = []
    for scenario in SCENARIOS:
        if only and scenario.tag not in only:
            continue
        started = time.perf_counter()
        result = await run_scenario(scenario, start_monday, weeks)
        print(f"== {scenario.tag}: {time.perf_counter() - started:.0f}s, errors {len(result['errors'])}", flush=True)
        results.append(result)

    async with AsyncSessionLocal() as session:
        exercises = (await session.execute(select(Exercise).where(Exercise.is_archived.is_(False)))).scalars().all()
    per_exercise = defaultdict(lambda: {"total": 0, "by_scenario": {}, "by_phase": Counter()})
    for result in results:
        for (exercise_id, phase), n in result["counts"].items():
            entry = per_exercise[exercise_id]
            entry["total"] += n
            entry["by_scenario"][result["tag"]] = entry["by_scenario"].get(result["tag"], 0) + n
            entry["by_phase"][phase] += n
    data = {
        "weeks": weeks,
        "scenarios": [{k: r[k] for k in ("tag", "description", "sessions")} | {"errors": r["errors"][:3]}
                      for r in results],
        "exercises": [
            {
                "id": str(e.id),
                "name": e.name,
                "phase": e.phase.value,
                "category": e.category.value,
                "difficulty": e.difficulty_level,
                "video": e.video_source_type is not None,
                "total": per_exercise[str(e.id)]["total"],
                "by_scenario": per_exercise[str(e.id)]["by_scenario"],
            }
            for e in exercises
        ],
    }
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written", out_path)


if __name__ == "__main__":
    asyncio.run(main())
