"""QuestService (app/services/quest_service.py) -- item 6c of the roadmap,
plus the 2026-08-30 claim-button follow-up.

Lazy read-time evaluation, same convention as has_missed_training_day /
ProgressService.get_streak: list_status checks each quest against current
data on every call and marks a newly-satisfied quest "claimable" the
moment it first becomes true, rather than via a background job or event
consumer. XP is only granted once the player explicitly calls claim() --
list_status never grants on its own.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.exercise import Exercise, ExerciseCategory, MovementPattern, TrainingPhase
from app.models.friend import FriendRequest, FriendRequestStatus
from app.models.quest import UserQuestCompletion
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.services.quest_service import ONE_TIME_PERIOD_KEY, QuestService

TODAY = date(2026, 3, 12)  # a Thursday
THIS_MONDAY = date(2026, 3, 9)


def _make_user(**kwargs) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"quest_{unique}",
        email=f"quest_{unique}@example.com",
        password_hash="irrelevant",
        **kwargs,
    )


def _make_exercise() -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )


async def _add_day_plan(
    db_session, user_id: uuid.UUID, *, day_date: date, session_type: DaySessionType
) -> DayPlan:
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user_id, week_start_date=day_date)
    db_session.add(weekly_plan)
    await db_session.flush()
    day_plan = DayPlan(
        id=uuid.uuid4(), weekly_plan_id=weekly_plan.id, date=day_date, session_type=session_type
    )
    db_session.add(day_plan)
    await db_session.flush()
    return day_plan


async def _add_completed_workout(
    db_session, user_id: uuid.UUID, exercise: Exercise, *, day_date: date
) -> TrainingSession:
    day_plan = await _add_day_plan(db_session, user_id, day_date=day_date, session_type=DaySessionType.OFF_ICE)
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
    return training_session


async def _add_incomplete_workout(
    db_session, user_id: uuid.UUID, exercise: Exercise, *, day_date: date
) -> None:
    day_plan = await _add_day_plan(db_session, user_id, day_date=day_date, session_type=DaySessionType.OFF_ICE)
    block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0)
    training_session = TrainingSession(id=uuid.uuid4(), day_plan_id=day_plan.id, blocks=[block])
    db_session.add(training_session)
    await db_session.flush()


def _status_by_id(statuses, quest_id: str):
    return next(s for s in statuses if s.id == quest_id)


# --- one-time quests: satisfying criteria makes a quest claimable ---


@pytest.mark.asyncio
async def test_diary_first_entry_claimable_once_an_entry_exists(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    session = await _add_completed_workout(db_session, user.id, exercise, day_date=TODAY)
    db_session.add(
        TrainingDiaryEntry(id=uuid.uuid4(), user_id=user.id, training_session_id=session.id, note="ok")
    )
    await db_session.flush()

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    status = _status_by_id(statuses, "diary_first_entry")
    assert status.claimable is True
    assert status.completed is False


@pytest.mark.asyncio
async def test_diary_first_entry_not_claimable_with_no_entries(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    status = _status_by_id(statuses, "diary_first_entry")
    assert status.claimable is False
    assert status.completed is False


@pytest.mark.asyncio
async def test_restriction_first_logged_claimable_once_a_restriction_exists(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserTemporaryRestriction(
            id=uuid.uuid4(),
            user_id=user.id,
            muscle_group=None,
            movement_pattern=list(MovementPattern)[0],
            expires_at=TODAY + timedelta(days=7),
        )
    )
    await db_session.flush()

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "restriction_first_logged").claimable is True


@pytest.mark.asyncio
async def test_first_friend_added_claimable_once_an_accepted_friend_exists(db_session) -> None:
    user = _make_user()
    other = _make_user()
    db_session.add_all([user, other])
    await db_session.flush()
    db_session.add(
        FriendRequest(
            sender_id=user.id, receiver_id=other.id, status=FriendRequestStatus.ACCEPTED
        )
    )
    await db_session.flush()

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "first_friend_added").claimable is True


@pytest.mark.asyncio
async def test_first_friend_added_not_claimable_for_pending_request(db_session) -> None:
    user = _make_user()
    other = _make_user()
    db_session.add_all([user, other])
    await db_session.flush()
    db_session.add(FriendRequest(sender_id=user.id, receiver_id=other.id))
    await db_session.flush()

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "first_friend_added").claimable is False


@pytest.mark.asyncio
async def test_first_full_workout_claimable_on_any_fully_completed_session(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _add_completed_workout(db_session, user.id, exercise, day_date=TODAY - timedelta(days=30))

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "first_full_workout").claimable is True


@pytest.mark.asyncio
async def test_first_full_workout_not_claimable_with_only_incomplete_sessions(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _add_incomplete_workout(db_session, user.id, exercise, day_date=TODAY)

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "first_full_workout").claimable is False


# --- weekly quests ---


@pytest.mark.asyncio
async def test_weekly_three_workouts_claimable_at_exactly_three(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    for offset in range(3):
        await _add_completed_workout(db_session, user.id, exercise, day_date=THIS_MONDAY + timedelta(days=offset))

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "weekly_three_workouts").claimable is True


@pytest.mark.asyncio
async def test_weekly_three_workouts_not_claimable_with_only_two(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    for offset in range(2):
        await _add_completed_workout(db_session, user.id, exercise, day_date=THIS_MONDAY + timedelta(days=offset))

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "weekly_three_workouts").claimable is False


@pytest.mark.asyncio
async def test_weekly_three_workouts_ignores_workouts_from_last_week(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    for offset in range(3):
        await _add_completed_workout(
            db_session, user.id, exercise, day_date=THIS_MONDAY - timedelta(days=7) + timedelta(days=offset)
        )

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "weekly_three_workouts").claimable is False


@pytest.mark.asyncio
async def test_weekly_no_missed_day_false_when_nothing_scheduled_yet(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "weekly_no_missed_day").claimable is False


@pytest.mark.asyncio
async def test_weekly_no_missed_day_true_when_all_scheduled_days_done(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _add_completed_workout(db_session, user.id, exercise, day_date=THIS_MONDAY)
    await _add_day_plan(db_session, user.id, day_date=THIS_MONDAY + timedelta(days=1), session_type=DaySessionType.REST)

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "weekly_no_missed_day").claimable is True


@pytest.mark.asyncio
async def test_weekly_no_missed_day_false_after_one_incomplete_training_day(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _add_completed_workout(db_session, user.id, exercise, day_date=THIS_MONDAY)
    await _add_incomplete_workout(db_session, user.id, exercise, day_date=THIS_MONDAY + timedelta(days=1))

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "weekly_no_missed_day").claimable is False


@pytest.mark.asyncio
async def test_weekly_restrictions_updated_true_for_restriction_created_this_week(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserTemporaryRestriction(
            id=uuid.uuid4(),
            user_id=user.id,
            movement_pattern=list(MovementPattern)[0],
            expires_at=TODAY + timedelta(days=7),
        )
    )
    await db_session.flush()

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "weekly_restrictions_updated").claimable is True


@pytest.mark.asyncio
async def test_weekly_restrictions_updated_false_for_older_restriction(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    restriction = UserTemporaryRestriction(
        id=uuid.uuid4(),
        user_id=user.id,
        movement_pattern=list(MovementPattern)[0],
        expires_at=TODAY + timedelta(days=7),
    )
    db_session.add(restriction)
    await db_session.flush()
    # Backdate created_at to before this week -- server_default only fires
    # on insert, so update it explicitly to simulate an old row.
    restriction.created_at = datetime.combine(
        THIS_MONDAY - timedelta(days=3), datetime.min.time(), tzinfo=timezone.utc
    )
    await db_session.flush()

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "weekly_restrictions_updated").claimable is False


# --- long-term quests ---


@pytest.mark.asyncio
async def test_monthly_no_big_gap_true_with_regular_workouts(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    for offset in range(0, 30, 2):
        await _add_completed_workout(db_session, user.id, exercise, day_date=TODAY - timedelta(days=offset))

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "monthly_no_big_gap").claimable is True


@pytest.mark.asyncio
async def test_monthly_no_big_gap_false_with_a_long_gap(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _add_completed_workout(db_session, user.id, exercise, day_date=TODAY)
    await _add_completed_workout(db_session, user.id, exercise, day_date=TODAY - timedelta(days=20))

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "monthly_no_big_gap").claimable is False


@pytest.mark.asyncio
async def test_monthly_no_big_gap_false_with_no_workouts(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "monthly_no_big_gap").claimable is False


@pytest.mark.asyncio
async def test_four_week_streak_goal_true_with_four_complete_prior_weeks(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    for weeks_back in range(1, 5):
        week_start = THIS_MONDAY - timedelta(days=7 * weeks_back)
        for offset in range(3):
            await _add_completed_workout(db_session, user.id, exercise, day_date=week_start + timedelta(days=offset))

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "four_week_streak_goal").claimable is True


@pytest.mark.asyncio
async def test_four_week_streak_goal_false_if_one_week_falls_short(db_session) -> None:
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    for weeks_back in range(1, 5):
        week_start = THIS_MONDAY - timedelta(days=7 * weeks_back)
        count = 2 if weeks_back == 2 else 3
        for offset in range(count):
            await _add_completed_workout(db_session, user.id, exercise, day_date=week_start + timedelta(days=offset))

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "four_week_streak_goal").claimable is False


@pytest.mark.asyncio
async def test_four_week_streak_goal_ignores_the_in_progress_current_week(db_session) -> None:
    """Loading up the *current* week with workouts must not substitute for
    a missing prior week -- only the 4 weeks strictly before this one
    count, so the goal can't flip true/false mid-week."""
    user = _make_user()
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    for offset in range(3):
        await _add_completed_workout(db_session, user.id, exercise, day_date=THIS_MONDAY + timedelta(days=offset))
    # Only 3 of the 4 required prior weeks are filled.
    for weeks_back in range(1, 4):
        week_start = THIS_MONDAY - timedelta(days=7 * weeks_back)
        for offset in range(3):
            await _add_completed_workout(db_session, user.id, exercise, day_date=week_start + timedelta(days=offset))

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "four_week_streak_goal").claimable is False


# --- claim(): XP, level-up, idempotency ---


@pytest.mark.asyncio
async def test_satisfying_a_quest_does_not_grant_xp_by_itself(db_session) -> None:
    user = _make_user(xp=0, level=1)
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _add_completed_workout(db_session, user.id, exercise, day_date=TODAY - timedelta(days=30))

    await QuestService(db_session).list_status(user.id, today=TODAY)

    await db_session.refresh(user)
    assert user.xp == 0


@pytest.mark.asyncio
async def test_claiming_a_claimable_quest_grants_its_xp(db_session) -> None:
    user = _make_user(xp=0, level=1)
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _add_completed_workout(db_session, user.id, exercise, day_date=TODAY - timedelta(days=30))

    service = QuestService(db_session)
    await service.list_status(user.id, today=TODAY)
    result = await service.claim(user.id, "first_full_workout", today=TODAY)

    assert result.completed is True
    assert result.claimable is False
    await db_session.refresh(user)
    assert user.xp == 50  # one_time reward


@pytest.mark.asyncio
async def test_claiming_an_already_claimed_quest_raises_and_does_not_double_pay(db_session) -> None:
    user = _make_user(xp=0, level=1)
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _add_completed_workout(db_session, user.id, exercise, day_date=TODAY - timedelta(days=30))

    service = QuestService(db_session)
    await service.list_status(user.id, today=TODAY)
    await service.claim(user.id, "first_full_workout", today=TODAY)

    with pytest.raises(HTTPException) as exc_info:
        await service.claim(user.id, "first_full_workout", today=TODAY)
    assert exc_info.value.status_code == 400

    await db_session.refresh(user)
    assert user.xp == 50


@pytest.mark.asyncio
async def test_claiming_a_not_yet_satisfied_quest_raises(db_session) -> None:
    user = _make_user(xp=0, level=1)
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await QuestService(db_session).claim(user.id, "diary_first_entry", today=TODAY)
    assert exc_info.value.status_code == 400

    await db_session.refresh(user)
    assert user.xp == 0


@pytest.mark.asyncio
async def test_claiming_an_unknown_quest_id_raises_404(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await QuestService(db_session).claim(user.id, "not_a_real_quest", today=TODAY)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_re_evaluating_a_claimable_quest_does_not_duplicate_the_row(db_session) -> None:
    user = _make_user(xp=0, level=1)
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    await _add_completed_workout(db_session, user.id, exercise, day_date=TODAY - timedelta(days=30))

    service = QuestService(db_session)
    await service.list_status(user.id, today=TODAY)
    await service.list_status(user.id, today=TODAY)

    result = await db_session.execute(
        select(UserQuestCompletion).where(
            UserQuestCompletion.user_id == user.id,
            UserQuestCompletion.quest_id == "first_full_workout",
        )
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_claim_xp_triggers_a_level_up_when_it_crosses_the_threshold(db_session) -> None:
    from app.events.handlers.block_completed import xp_to_next_level

    threshold = xp_to_next_level(1)
    user = _make_user(xp=threshold - 10, level=1)
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    # first_full_workout (50 XP, > the 10 needed to cross the threshold)
    await _add_completed_workout(db_session, user.id, exercise, day_date=TODAY - timedelta(days=30))

    service = QuestService(db_session)
    await service.list_status(user.id, today=TODAY)
    await service.claim(user.id, "first_full_workout", today=TODAY)

    await db_session.refresh(user)
    assert user.level == 2
    assert user.xp == (threshold - 10) + 50 - threshold


@pytest.mark.asyncio
async def test_weekly_quest_can_be_earned_again_in_a_later_week(db_session) -> None:
    user = _make_user(xp=0, level=1)
    exercise = _make_exercise()
    db_session.add_all([user, exercise])
    await db_session.flush()
    for offset in range(3):
        await _add_completed_workout(db_session, user.id, exercise, day_date=THIS_MONDAY + timedelta(days=offset))

    service = QuestService(db_session)
    week1_statuses = await service.list_status(user.id, today=TODAY)
    assert _status_by_id(week1_statuses, "weekly_three_workouts").claimable is True
    await service.claim(user.id, "weekly_three_workouts", today=TODAY)

    next_monday = THIS_MONDAY + timedelta(days=7)
    next_today = TODAY + timedelta(days=7)
    for offset in range(3):
        await _add_completed_workout(db_session, user.id, exercise, day_date=next_monday + timedelta(days=offset))

    week2_statuses = await service.list_status(user.id, today=next_today)
    assert _status_by_id(week2_statuses, "weekly_three_workouts").claimable is True
    await service.claim(user.id, "weekly_three_workouts", today=next_today)

    # Two distinct periods -> two separate completion rows, not one row
    # reused/blocked by the uniqueness constraint.
    result = await db_session.execute(
        select(UserQuestCompletion.period_key).where(
            UserQuestCompletion.user_id == user.id,
            UserQuestCompletion.quest_id == "weekly_three_workouts",
        )
    )
    assert sorted(row[0] for row in result.all()) == sorted([THIS_MONDAY, next_monday])


@pytest.mark.asyncio
async def test_claimed_quest_stays_completed_in_status_list(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserQuestCompletion(
            id=uuid.uuid4(),
            user_id=user.id,
            quest_id="diary_first_entry",
            period_key=ONE_TIME_PERIOD_KEY,
            xp_awarded=50,
            claimed_at=datetime.now(timezone.utc),
        )
    )
    await db_session.flush()

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    status = _status_by_id(statuses, "diary_first_entry")
    assert status.completed is True
    assert status.claimable is False


@pytest.mark.asyncio
async def test_unclaimed_satisfied_row_shows_as_claimable_not_completed(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserQuestCompletion(
            id=uuid.uuid4(),
            user_id=user.id,
            quest_id="diary_first_entry",
            period_key=ONE_TIME_PERIOD_KEY,
            xp_awarded=50,
            claimed_at=None,
        )
    )
    await db_session.flush()

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    status = _status_by_id(statuses, "diary_first_entry")
    assert status.completed is False
    assert status.claimable is True


# --- reference_first_visit / mark_reference_visited ---


@pytest.mark.asyncio
async def test_reference_first_visit_not_claimable_until_marked(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    status = _status_by_id(statuses, "reference_first_visit")
    assert status.claimable is False
    assert status.completed is False


@pytest.mark.asyncio
async def test_mark_reference_visited_makes_the_quest_claimable_but_does_not_grant_xp(db_session) -> None:
    user = _make_user(xp=0, level=1)
    db_session.add(user)
    await db_session.flush()

    await QuestService(db_session).mark_reference_visited(user.id)

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)
    status = _status_by_id(statuses, "reference_first_visit")
    assert status.claimable is True
    assert status.completed is False
    await db_session.refresh(user)
    assert user.xp == 0


@pytest.mark.asyncio
async def test_claiming_reference_first_visit_after_marking_grants_xp(db_session) -> None:
    user = _make_user(xp=0, level=1)
    db_session.add(user)
    await db_session.flush()

    service = QuestService(db_session)
    await service.mark_reference_visited(user.id)
    await service.claim(user.id, "reference_first_visit", today=TODAY)

    await db_session.refresh(user)
    assert user.xp == 50


@pytest.mark.asyncio
async def test_mark_reference_visited_is_idempotent(db_session) -> None:
    user = _make_user(xp=0, level=1)
    db_session.add(user)
    await db_session.flush()

    service = QuestService(db_session)
    await service.mark_reference_visited(user.id)
    await service.mark_reference_visited(user.id)

    result = await db_session.execute(
        select(UserQuestCompletion).where(
            UserQuestCompletion.user_id == user.id,
            UserQuestCompletion.quest_id == "reference_first_visit",
        )
    )
    assert len(result.scalars().all()) == 1


# --- period_start / type shape ---


@pytest.mark.asyncio
async def test_one_time_quest_has_no_period_start_weekly_quest_does(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    statuses = await QuestService(db_session).list_status(user.id, today=TODAY)

    assert _status_by_id(statuses, "diary_first_entry").period_start is None
    assert _status_by_id(statuses, "weekly_three_workouts").period_start == THIS_MONDAY.isoformat()
