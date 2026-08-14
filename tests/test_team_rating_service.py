"""TeamRatingService: team_score = sum(member.xp) * (1 + activity_bonus),
activity_bonus = min(avg_trainings_per_member_per_week / 4, 1) * 0.15.

Scenarios below use real numbers (not just "score A > score B") so the
formula's actual behavior is visible: sum_xp dominates activity_bonus (a
20-person team half as active per-member can still outrank an 8-person team
at max activity, simply because it has 20x the raw xp). Same db_session
fixture (real Postgres, rolled back per test) as test_has_missed_training_day.py
and test_team_service.py; team membership is inserted directly rather than
through TeamService's join/approve flow, since that flow isn't what's under
test here.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TrainingPhase
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.services.team_rating_service import TeamRatingService

TODAY = date.today()


def _make_user(xp: int) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"rating_{unique}",
        email=f"rating_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        xp=xp,
    )


def _make_exercise() -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=3,
        equipment_type=EquipmentType.GYM,
    )


async def _add_team(db_session, name: str, members: list[User]) -> Team:
    team = Team(
        id=uuid.uuid4(),
        name=name,
        owner_id=members[0].id,
        invite_code=uuid.uuid4().hex[:16].upper(),
    )
    db_session.add(team)
    await db_session.flush()
    for member in members:
        db_session.add(TeamMembership(id=uuid.uuid4(), team_id=team.id, user_id=member.id))
    await db_session.flush()
    return team


async def _add_completed_training(db_session, user_id: uuid.UUID, exercise: Exercise, day_date: date) -> None:
    # Same shape as test_has_missed_training_day._add_day_plan /
    # _add_completed_block: a WeeklyPlan keyed off the day's own date avoids
    # (user_id, week_start_date) collisions between the multiple trainings
    # seeded per user below.
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user_id, week_start_date=day_date)
    db_session.add(weekly_plan)
    await db_session.flush()
    day_plan = DayPlan(
        id=uuid.uuid4(),
        weekly_plan_id=weekly_plan.id,
        date=day_date,
        session_type=DaySessionType.OFF_ICE,
    )
    db_session.add(day_plan)
    await db_session.flush()
    block = SessionBlock(
        id=uuid.uuid4(),
        phase=TrainingPhase.MAIN,
        exercise_id=exercise.id,
        order=0,
        completed_at=datetime.now(timezone.utc),
    )
    training_session = TrainingSession(id=uuid.uuid4(), day_plan_id=day_plan.id, blocks=[block])
    db_session.add(training_session)
    await db_session.flush()


@pytest.mark.asyncio
async def test_score_with_no_activity_has_zero_bonus(db_session) -> None:
    members = [_make_user(xp=100) for _ in range(8)]
    db_session.add_all(members)
    await db_session.flush()
    team = await _add_team(db_session, "Idle Eights", members)

    score = await TeamRatingService(db_session).compute_team_score(team)

    assert score.sum_xp == 800
    assert score.member_count == 8
    assert score.avg_trainings_per_member_per_week == 0.0
    assert score.activity_bonus == 0.0
    assert score.team_score == 800.0


@pytest.mark.asyncio
async def test_score_at_full_activity_caps_bonus_at_15_percent(db_session) -> None:
    # 8 members, each with 4 completed trainings this week -> avg == 4.0,
    # exactly the target -> activity_bonus hits its 0.15 cap.
    exercise = _make_exercise()
    members = [_make_user(xp=100) for _ in range(8)]
    db_session.add_all([exercise, *members])
    await db_session.flush()
    for member in members:
        for offset in range(4):
            await _add_completed_training(db_session, member.id, exercise, TODAY - timedelta(days=offset))
    team = await _add_team(db_session, "Sharks", members)

    score = await TeamRatingService(db_session).compute_team_score(team)

    assert score.sum_xp == 800
    assert score.avg_trainings_per_member_per_week == 4.0
    assert score.activity_bonus == 0.15
    assert score.team_score == 920.0  # 800 * 1.15


@pytest.mark.asyncio
async def test_score_with_partial_activity_is_between_the_two_extremes(db_session) -> None:
    # 20 members, xp=50 each (sum_xp=1000). Half train 4x this week, half
    # train 0x -> total completed trainings = 40, avg = 40/20 = 2.0 (half of
    # the 4/week target) -> activity_bonus = 0.075 (half of the 0.15 cap).
    exercise = _make_exercise()
    members = [_make_user(xp=50) for _ in range(20)]
    db_session.add_all([exercise, *members])
    await db_session.flush()
    for member in members[:10]:
        for offset in range(4):
            await _add_completed_training(db_session, member.id, exercise, TODAY - timedelta(days=offset))
    # members[10:] stay fully inactive -- still counted in member_count.
    team = await _add_team(db_session, "Wolves", members)

    score = await TeamRatingService(db_session).compute_team_score(team)

    assert score.sum_xp == 1000
    assert score.member_count == 20
    assert score.avg_trainings_per_member_per_week == 2.0
    assert score.activity_bonus == 0.075
    assert score.team_score == 1075.0  # 1000 * 1.075


@pytest.mark.asyncio
async def test_training_older_than_7_days_does_not_count(db_session) -> None:
    exercise = _make_exercise()
    members = [_make_user(xp=100) for _ in range(8)]
    db_session.add_all([exercise, *members])
    await db_session.flush()
    # 8 days ago is outside the 7-day window (today, and the 6 days before).
    await _add_completed_training(db_session, members[0].id, exercise, TODAY - timedelta(days=8))
    team = await _add_team(db_session, "Stale Eights", members)

    score = await TeamRatingService(db_session).compute_team_score(team)

    assert score.avg_trainings_per_member_per_week == 0.0
    assert score.activity_bonus == 0.0


@pytest.mark.asyncio
async def test_rankings_exclude_teams_under_8_members_even_with_a_higher_score(db_session) -> None:
    small_members = [_make_user(xp=1000) for _ in range(5)]
    big_members = [_make_user(xp=100) for _ in range(8)]
    db_session.add_all([*small_members, *big_members])
    await db_session.flush()
    small_team = await _add_team(db_session, "Cubs", small_members)
    big_team = await _add_team(db_session, "Sharks", big_members)

    service = TeamRatingService(db_session)
    small_score = await service.compute_team_score(small_team)
    assert small_score.team_score == 5000.0  # own score is still computable...

    rankings = await service.get_team_rankings(limit=50, offset=0)
    ranked_ids = {entry.team_id for entry in rankings}
    assert small_team.id not in ranked_ids  # ...but excluded from the cross-team top
    assert big_team.id in ranked_ids


@pytest.mark.asyncio
async def test_rankings_are_sorted_by_team_score_descending(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)

    sharks_members = [_make_user(xp=100) for _ in range(8)]
    wolves_members = [_make_user(xp=50) for _ in range(20)]
    db_session.add_all([*sharks_members, *wolves_members])
    await db_session.flush()

    for member in sharks_members:
        for offset in range(4):
            await _add_completed_training(db_session, member.id, exercise, TODAY - timedelta(days=offset))
    for member in wolves_members[:10]:
        for offset in range(4):
            await _add_completed_training(db_session, member.id, exercise, TODAY - timedelta(days=offset))

    sharks = await _add_team(db_session, "Sharks", sharks_members)
    wolves = await _add_team(db_session, "Wolves", wolves_members)

    rankings = await TeamRatingService(db_session).get_team_rankings(limit=50, offset=0)
    ranked_ids = [entry.team_id for entry in rankings]

    # Wolves (1075.0) outranks Sharks (920.0) despite a lower per-member
    # activity bonus (0.075 vs 0.15) -- sum_xp is what dominates the formula.
    assert ranked_ids.index(wolves.id) < ranked_ids.index(sharks.id)
