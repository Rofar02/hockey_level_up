"""AnalyticsOverviewService: the Analytics screen's numbers, all derived
from what the app already records -- blocks left undone per stat, records
against earlier bests, regularity and its calendar, the weekly load
warning, muscle balance, and the findings built from them.

The user is on UTC so "today" is the same instant for the fixtures and the
service (see the local-midnight note in project memory).
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseMuscleGroup,
    ExerciseTargetStat,
    MovementPattern,
    MuscleGroup,
    TargetStat,
    TrainingPhase,
)
from app.models.progress import StatHistory, UserStat
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion, SetFeedback
from app.models.user import User
from app.services.analytics_overview_service import AnalyticsOverviewService

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()


def _user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"overview_{unique}",
        email=f"overview_{unique}@example.com",
        password_hash="irrelevant",
        timezone="UTC",
        has_premium=True,
    )


def _exercise(name: str, stat: TargetStat, *, pattern: MovementPattern | None = None, muscle: MuscleGroup | None = None):
    exercise = Exercise(
        id=uuid.uuid4(),
        name=f"{name} {uuid.uuid4().hex[:6]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=2,
    )
    rows = [ExerciseTargetStat(exercise_id=exercise.id, target_stat=stat, order=0)]
    if pattern is not None:
        rows.append(ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=pattern))
    if muscle is not None:
        rows.append(ExerciseMuscleGroup(exercise_id=exercise.id, muscle_group=muscle, weight=1.0))
    return exercise, rows


class _Plans:
    """Day plans for one user, one WeeklyPlan per Monday-started week."""

    def __init__(self, db_session, user: User) -> None:
        self._db = db_session
        self._user = user
        self._weeks: dict[date, WeeklyPlan] = {}

    async def day(
        self,
        on: date,
        blocks: list[tuple[Exercise, str]],
        session_type: DaySessionType = DaySessionType.OFF_ICE,
    ) -> TrainingSession:
        week_start = on - timedelta(days=on.weekday())
        week = self._weeks.get(week_start)
        if week is None:
            week = WeeklyPlan(id=uuid.uuid4(), user_id=self._user.id, week_start_date=week_start)
            self._db.add(week)
            await self._db.flush()
            self._weeks[week_start] = week
        done_at = datetime.combine(on, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=12)
        session = TrainingSession(
            id=uuid.uuid4(),
            blocks=[
                SessionBlock(
                    id=uuid.uuid4(),
                    phase=TrainingPhase.MAIN,
                    exercise_id=exercise.id,
                    order=index,
                    completed_at=done_at if state == "done" else None,
                )
                for index, (exercise, state) in enumerate(blocks)
            ],
        )
        self._db.add(
            DayPlan(id=uuid.uuid4(), weekly_plan_id=week.id, date=on, session_type=session_type, training_session=session)
        )
        await self._db.flush()
        return session


@pytest.mark.asyncio
async def test_skipped_blocks_regularity_and_most_skipped(db_session) -> None:
    user = _user()
    squat, squat_rows = _exercise("Присед", TargetStat.STRENGTH)
    burpee, burpee_rows = _exercise("Бёрпи", TargetStat.ENDURANCE)
    db_session.add_all([user, squat, burpee])
    await db_session.flush()
    db_session.add_all(squat_rows + burpee_rows)
    plans = _Plans(db_session, user)

    # Trained but left burpees twice; missed one whole day; a rest day.
    await plans.day(TODAY - timedelta(days=6), [(squat, "done"), (burpee, "open")])
    await plans.day(TODAY - timedelta(days=4), [(squat, "done"), (burpee, "open")])
    await plans.day(TODAY - timedelta(days=2), [(squat, "open"), (burpee, "open")])
    await plans.day(TODAY - timedelta(days=1), [], DaySessionType.REST)

    overview = await AnalyticsOverviewService(db_session).get_overview(user, 30)

    by_stat = {stat.stat: stat for stat in overview.stats}
    assert by_stat["endurance"].planned_blocks == 3
    assert by_stat["endurance"].skipped_dates == [
        TODAY - timedelta(days=6),
        TODAY - timedelta(days=4),
        TODAY - timedelta(days=2),
    ]
    assert by_stat["strength"].skipped_dates == [TODAY - timedelta(days=2)]

    regularity = overview.regularity
    assert (regularity.completed_sessions, regularity.planned_sessions) == (2, 3)
    # Only the days the player trained: the fully missed day isn't a choice.
    assert [(item.exercise_name, item.count) for item in regularity.most_skipped] == [(burpee.name, 2)]
    statuses = {day.date: day.status for day in regularity.calendar}
    assert statuses[TODAY - timedelta(days=6)] == "done"
    assert statuses[TODAY - timedelta(days=2)] == "skipped"
    assert statuses[TODAY - timedelta(days=1)] == "rest"
    assert len(regularity.calendar) == 28
    assert regularity.team_going is None


@pytest.mark.asyncio
async def test_records_beat_an_earlier_best_in_the_same_unit(db_session) -> None:
    user = _user()
    squat, squat_rows = _exercise("Присед", TargetStat.STRENGTH)
    plank, plank_rows = _exercise("Планка", TargetStat.ENDURANCE)
    new_one, new_rows = _exercise("Новое", TargetStat.AGILITY)
    db_session.add_all([user, squat, plank, new_one])
    await db_session.flush()
    db_session.add_all(squat_rows + plank_rows + new_rows)
    plans = _Plans(db_session, user)
    old = await plans.day(TODAY - timedelta(days=45), [(squat, "done"), (plank, "done")])
    recent = await plans.day(TODAY - timedelta(days=3), [(squat, "done"), (plank, "done"), (new_one, "done")])

    def logged(session, exercise, number, days_ago, **values):
        return SetCompletion(
            user_id=user.id,
            exercise_id=exercise.id,
            training_session_id=session.id,
            set_number=number,
            completed_at=NOW - timedelta(days=days_ago),
            **values,
        )

    db_session.add_all(
        [
            logged(old, squat, 1, 45, weight_kg=60.0, reps_completed=8),
            logged(old, plank, 1, 45, duration_seconds_completed=70),
            logged(recent, squat, 1, 3, weight_kg=65.0, reps_completed=8),
            logged(recent, squat, 2, 3, weight_kg=67.5, reps_completed=6),
            logged(recent, plank, 1, 3, duration_seconds_completed=60),
            logged(recent, new_one, 1, 3, reps_completed=20),
        ]
    )
    await db_session.flush()

    overview = await AnalyticsOverviewService(db_session).get_overview(user, 30)

    # Squat improved; the plank got worse; a first-ever exercise is no record.
    assert [(record.exercise_name, record.unit, record.before, record.after) for record in overview.records] == [
        (squat.name, "kg", 60.0, 67.5)
    ]
    records_insight = next(insight for insight in overview.insights if insight.kind == "records")
    assert records_insight.title == "1 новый рекорд"
    assert "67,5 кг" in records_insight.detail
    assert records_insight.action == "records"


@pytest.mark.asyncio
async def test_load_warning_when_work_and_hard_ratings_both_climb(db_session) -> None:
    user = _user()
    squat, squat_rows = _exercise("Присед", TargetStat.STRENGTH)
    db_session.add_all([user, squat])
    await db_session.flush()
    db_session.add_all(squat_rows)
    plans = _Plans(db_session, user)

    this_monday = TODAY - timedelta(days=TODAY.weekday())
    week_before = this_monday - timedelta(weeks=2)
    last_week = this_monday - timedelta(weeks=1)

    async def week_of_sets(monday: date, count: int, hard: int) -> None:
        session = await plans.day(monday + timedelta(days=1), [(squat, "done")])
        at = datetime.combine(monday + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
        db_session.add_all(
            [
                SetCompletion(
                    user_id=user.id,
                    exercise_id=squat.id,
                    training_session_id=session.id,
                    set_number=number + 1,
                    weight_kg=60.0,
                    reps_completed=8,
                    feedback=SetFeedback.HARD if number < hard else SetFeedback.NORMAL,
                    completed_at=at,
                )
                for number in range(count)
            ]
        )
        await db_session.flush()

    await week_of_sets(week_before, 10, 2)
    await week_of_sets(last_week, 12, 6)

    overview = await AnalyticsOverviewService(db_session).get_overview(user, 30)

    weeks = {week.week_start: week for week in overview.load.weeks}
    assert weeks[last_week].tonnage_kg == 12 * 60 * 8
    assert weeks[last_week].hard_share == 0.5
    assert overview.load.warning is not None
    assert "+20%" in overview.load.warning


@pytest.mark.asyncio
async def test_balance_notes_too_little_pulling(db_session) -> None:
    user = _user()
    press, press_rows = _exercise("Жим", TargetStat.STRENGTH, pattern=MovementPattern.PUSH, muscle=MuscleGroup.CHEST)
    row, row_rows = _exercise("Тяга", TargetStat.STRENGTH, pattern=MovementPattern.PULL, muscle=MuscleGroup.BACK)
    db_session.add_all([user, press, row])
    await db_session.flush()
    db_session.add_all(press_rows + row_rows)
    plans = _Plans(db_session, user)
    for offset in range(1, 6):
        await plans.day(TODAY - timedelta(days=offset * 2), [(press, "done"), (press, "done")] + ([(row, "done")] if offset <= 2 else []))

    overview = await AnalyticsOverviewService(db_session).get_overview(user, 30)

    assert (overview.balance.push_blocks, overview.balance.pull_blocks) == (10, 2)
    assert overview.balance.note is not None and overview.balance.note.startswith("Тянущих упражнений меньше")
    shares = {group.group: group.share for group in overview.balance.groups}
    assert shares["chest_shoulders"] == pytest.approx(10 / 12)
    assert shares["back"] == pytest.approx(2 / 12)


@pytest.mark.asyncio
async def test_decline_insight_names_the_skipped_blocks_and_asks_the_coach(db_session) -> None:
    user = _user()
    run, run_rows = _exercise("Челночный бег", TargetStat.ENDURANCE)
    db_session.add_all([user, run])
    await db_session.flush()
    db_session.add_all(run_rows)
    db_session.add_all(
        [
            UserStat(user_id=user.id, stat_type=TargetStat.ENDURANCE, current_value=50.0, last_updated_at=NOW),
            StatHistory(user_id=user.id, stat_type=TargetStat.ENDURANCE, value=62.0, recorded_at=NOW - timedelta(days=31), reason="test"),
            StatHistory(user_id=user.id, stat_type=TargetStat.ENDURANCE, value=50.0, recorded_at=NOW, reason="test"),
        ]
    )
    plans = _Plans(db_session, user)
    await plans.day(TODAY - timedelta(days=5), [(run, "open")])
    await plans.day(TODAY - timedelta(days=3), [(run, "done")])

    overview = await AnalyticsOverviewService(db_session).get_overview(user, 30)

    decline = overview.insights[0]
    assert decline.kind == "decline"
    assert decline.title.startswith("Выносливость просела на")
    assert decline.detail == "Пропущено 1 блок на неё из 2."
    assert decline.action == "ask_coach"
    assert decline.coach_prompt is not None and "выносливость" in decline.coach_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stat", "title", "pronoun", "prompt"),
    [
        (TargetStat.INTELLECT, "Интеллект просел на", "на него", "у меня просел интеллект"),
        (TargetStat.PUCK_HANDLING, "Владение шайбой просело на", "на него", "у меня просело владение шайбой"),
    ],
)
async def test_decline_wording_agrees_with_the_stat(db_session, stat, title, pronoun, prompt) -> None:
    user = _user()
    drill, drill_rows = _exercise("Упражнение", stat)
    db_session.add_all([user, drill])
    await db_session.flush()
    db_session.add_all(drill_rows)
    db_session.add_all(
        [
            UserStat(user_id=user.id, stat_type=stat, current_value=50.0, last_updated_at=NOW),
            StatHistory(user_id=user.id, stat_type=stat, value=62.0, recorded_at=NOW - timedelta(days=31), reason="test"),
            StatHistory(user_id=user.id, stat_type=stat, value=50.0, recorded_at=NOW, reason="test"),
        ]
    )
    await _Plans(db_session, user).day(TODAY - timedelta(days=5), [(drill, "open")])

    overview = await AnalyticsOverviewService(db_session).get_overview(user, 30)

    decline = overview.insights[0]
    assert decline.title.startswith(title)
    assert pronoun in decline.detail
    assert decline.coach_prompt is not None and prompt in decline.coach_prompt
