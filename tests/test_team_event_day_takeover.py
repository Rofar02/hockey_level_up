"""A team event the player marked "going" takes their own day over
(TRAINING -> ON_ICE, GAME -> GAME) and gives it back on "not going",
cleared attendance, cancel or reschedule -- see
ScheduleService.apply_team_event_to_day / revert_team_event_days.
"""
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.models.exercise import Exercise, ExerciseCategory, TrainingPhase
from app.models.schedule import (
    DayPlan,
    DaySessionType,
    SessionBlock,
    TrainingBlock,
    TrainingSession,
    WeeklyPlan,
)
from app.models.team_event import TeamEventAbsenceReason, TeamEventAttendanceStatus, TeamEventType
from app.models.user import User
from app.repositories.schedule_repository import ScheduleRepository
from app.schemas.schedule import DayPlanIn, WeeklyPlanCreate
from app.services.schedule_service import ScheduleService
from app.services.team_event_service import TeamEventService
from app.services.team_service import TeamService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"takeover_{unique}",
        email=f"takeover_{unique}@example.com",
        password_hash="irrelevant",
        timezone="UTC",
    )


def _monday_of(reference: date) -> date:
    return reference - timedelta(days=reference.weekday())


def _noon_utc(day: date) -> datetime:
    return datetime.combine(day, time(12, 0), tzinfo=timezone.utc)


async def _make_team_with_player(db_session):
    captain = _make_user()
    player = _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()

    teams = TeamService(db_session)
    team = await teams.create_team(captain, "Sharks")
    request = await teams.join_by_code(player, team.invite_code)
    await teams.approve_request(captain, request.id)
    return captain, player, team


async def _declare_rest_week(db_session, user: User, any_day: date, block_number: int = 1) -> None:
    monday = _monday_of(any_day)
    block = TrainingBlock(
        id=uuid.uuid4(), user_id=user.id, block_number=block_number, phase_started_at=monday
    )
    db_session.add(block)
    await db_session.flush()
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=monday, training_block_id=block.id
    )
    for offset in range(7):
        weekly_plan.day_plans.append(
            DayPlan(id=uuid.uuid4(), date=monday + timedelta(days=offset), session_type=DaySessionType.REST)
        )
    db_session.add(weekly_plan)
    await db_session.flush()


async def _day(db_session, user: User, day: date) -> DayPlan:
    day_plan = await ScheduleRepository(db_session).get_day_plan_for_date(user.id, day)
    await db_session.refresh(day_plan)
    return day_plan


def _event_day() -> date:
    return date.today() + timedelta(days=2)


@pytest.mark.asyncio
async def test_going_turns_day_into_on_ice_and_not_going_restores_it(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event_day = _event_day()
    await _declare_rest_week(db_session, player, event_day)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _noon_utc(event_day), None)

    await events.set_my_attendance(player, team.id, event.id, TeamEventAttendanceStatus.GOING, None, None)
    day_plan = await _day(db_session, player, event_day)
    assert day_plan.session_type == DaySessionType.ON_ICE
    assert day_plan.team_event_id == event.id
    assert day_plan.replaced_session_type == DaySessionType.REST

    await events.set_my_attendance(
        player, team.id, event.id, TeamEventAttendanceStatus.NOT_GOING, TeamEventAbsenceReason.WORK, None
    )
    day_plan = await _day(db_session, player, event_day)
    assert day_plan.session_type == DaySessionType.REST
    assert day_plan.team_event_id is None
    assert day_plan.replaced_session_type is None


@pytest.mark.asyncio
async def test_game_turns_day_into_game(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event_day = _event_day()
    await _declare_rest_week(db_session, player, event_day)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.GAME, _noon_utc(event_day), "Wolves")

    await events.set_my_attendance(player, team.id, event.id, TeamEventAttendanceStatus.GOING, None, None)

    day_plan = await _day(db_session, player, event_day)
    assert day_plan.session_type == DaySessionType.GAME
    assert day_plan.team_event_id == event.id


@pytest.mark.asyncio
async def test_clearing_attendance_and_cancelling_both_restore_the_day(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event_day = _event_day()
    await _declare_rest_week(db_session, player, event_day)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _noon_utc(event_day), None)

    await events.set_my_attendance(player, team.id, event.id, TeamEventAttendanceStatus.GOING, None, None)
    await events.clear_my_attendance(player, team.id, event.id)
    assert (await _day(db_session, player, event_day)).session_type == DaySessionType.REST

    await events.set_my_attendance(player, team.id, event.id, TeamEventAttendanceStatus.GOING, None, None)
    await events.cancel_event(captain, team.id, event.id)
    day_plan = await _day(db_session, player, event_day)
    assert day_plan.session_type == DaySessionType.REST
    assert day_plan.team_event_id is None


@pytest.mark.asyncio
async def test_reschedule_moves_the_takeover_to_the_new_day(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    old_day = _event_day()
    new_day = old_day + timedelta(days=1)
    await _declare_rest_week(db_session, player, old_day)
    if _monday_of(new_day) != _monday_of(old_day):
        await _declare_rest_week(db_session, player, new_day, block_number=2)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _noon_utc(old_day), None)
    await events.set_my_attendance(player, team.id, event.id, TeamEventAttendanceStatus.GOING, None, None)

    await events.reschedule_event(captain, team.id, event.id, _noon_utc(new_day))

    assert (await _day(db_session, player, old_day)).session_type == DaySessionType.REST
    moved = await _day(db_session, player, new_day)
    assert moved.session_type == DaySessionType.ON_ICE
    assert moved.team_event_id == event.id


@pytest.mark.asyncio
async def test_started_day_is_left_alone(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event_day = _event_day()
    await _declare_rest_week(db_session, player, event_day)
    exercise = Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )
    db_session.add(exercise)
    await db_session.flush()
    day_plan = await _day(db_session, player, event_day)
    day_plan.session_type = DaySessionType.OFF_ICE
    db_session.add(
        TrainingSession(
            id=uuid.uuid4(),
            day_plan_id=day_plan.id,
            blocks=[
                SessionBlock(
                    id=uuid.uuid4(),
                    phase=TrainingPhase.MAIN,
                    exercise_id=exercise.id,
                    order=0,
                    completed_at=date.today(),
                )
            ],
        )
    )
    await db_session.flush()
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _noon_utc(event_day), None)

    await events.set_my_attendance(player, team.id, event.id, TeamEventAttendanceStatus.GOING, None, None)

    day_plan = await _day(db_session, player, event_day)
    assert day_plan.session_type == DaySessionType.OFF_ICE
    assert day_plan.team_event_id is None


@pytest.mark.asyncio
async def test_week_declared_after_going_starts_with_the_takeover(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    # A week that isn't declared yet when the player answers.
    monday = _monday_of(date.today()) + timedelta(days=7)
    event_day = monday + timedelta(days=2)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _noon_utc(event_day), None)
    await events.set_my_attendance(player, team.id, event.id, TeamEventAttendanceStatus.GOING, None, None)

    payload = WeeklyPlanCreate(
        days=[
            DayPlanIn(date=monday + timedelta(days=offset), session_type=DaySessionType.REST)
            for offset in range(7)
        ]
    )
    weekly_plan = await ScheduleService(db_session).create_weekly_plan(player, payload)

    by_date = {day.date: day for day in weekly_plan.day_plans}
    assert by_date[event_day].session_type == DaySessionType.ON_ICE
    assert by_date[event_day].team_event_id == event.id
    assert by_date[event_day + timedelta(days=1)].session_type == DaySessionType.REST

    day_plan = await _day(db_session, player, event_day)
    assert day_plan.replaced_session_type == DaySessionType.REST
