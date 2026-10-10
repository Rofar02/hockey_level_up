"""The dev-branch review before the merge (2026-10-10): one test per item.

Joint trainings (1, 5), the ice charge on the muscle map (2, 3), the
coach's weekly tasks (4), the coach follow-up call (7), «Мой сезон» (8),
the streak and a double day (9), the week-load shadow (12).
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.coach_tasks import CoachTaskSpec, CoachTaskType
from app.core.muscle_load import MAX_INTENSITY
from app.models.exercise import MuscleGroup
from app.models.progress import IceLoadCharge, UserMuscleLoad
from app.models.push_subscription import PushSubscription
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.team_event import (
    TeamEventAbsenceReason,
    TeamEventAttendanceStatus,
    TeamEventPublishStatus,
    TeamEventType,
    TeamIceScheduleTemplate,
)
from app.models.user import SeasonPeriod, User
from app.services import coach_chat_service, team_event_service
from app.services.coach_task_service import CoachTaskService
from app.services.ice_load_service import IceLoadService
from app.services.joint_training_service import JointTrainingService
from app.services.season_summary_service import summary_available, team_most_stable_line
from app.services.streak_service import has_missed_training_day
from app.services.team_event_service import TeamEventService
from app.services.team_service import TeamService
from app.services.week_load_service import shadow_check
from tests.dates import utc_today


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(id=uuid.uuid4(), username=f"rv_{unique}", email=f"rv_{unique}@example.com", password_hash="x", timezone="UTC")
    defaults.update(overrides)
    return User(**defaults)


async def _team(db_session, name: str):
    captain, player = _make_user(), _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()
    teams = TeamService(db_session)
    team = await teams.create_team(captain, name)
    request = await teams.join_by_code(player, team.invite_code)
    await teams.approve_request(captain, request.id)
    return captain, player, team


def _future(days: int = 2) -> datetime:
    return datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=days)


async def _joint(db_session):
    host_captain, host_player, host = await _team(db_session, "Хозяева")
    guest_captain, guest_player, guest = await _team(db_session, "Гости")
    events = TeamEventService(db_session)
    event = await events.create_event(host_captain, host.id, TeamEventType.TRAINING, _future(), None)
    joint = JointTrainingService(db_session)
    await joint.invite_to_event(host_captain, host.id, event.id, guest.id)
    invitation = (await joint.list_incoming(guest_captain, guest.id))[0]
    await joint.answer(guest_captain, guest.id, invitation.id, accept=True)
    return host_captain, host_player, host, guest_captain, guest_player, guest, event, invitation


# -- 1 --


@pytest.mark.asyncio
async def test_answer_only_a_pending_invitation_to_a_training_ahead(db_session) -> None:
    host_captain, _, host = await _team(db_session, "Хозяева")
    guest_captain, _, guest = await _team(db_session, "Гости")
    events = TeamEventService(db_session)
    event = await events.create_event(host_captain, host.id, TeamEventType.TRAINING, _future(), None)
    joint = JointTrainingService(db_session)
    await joint.invite_to_event(host_captain, host.id, event.id, guest.id)
    invitation = (await joint.list_incoming(guest_captain, guest.id))[0]
    await joint.answer(guest_captain, guest.id, invitation.id, accept=False)

    # Already answered -- can't be accepted later.
    with pytest.raises(HTTPException) as exc:
        await joint.answer(guest_captain, guest.id, invitation.id, accept=True)
    assert exc.value.status_code == 409

    # Re-invited, then the host cancels the training: no accepting it.
    await joint.invite_to_event(host_captain, host.id, event.id, guest.id)
    await events.cancel_event(host_captain, host.id, event.id)
    with pytest.raises(HTTPException) as exc:
        await joint.answer(guest_captain, guest.id, invitation.id, accept=True)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_host_removes_a_guest_team(db_session) -> None:
    host_captain, _, host, guest_captain, guest_player, guest, event, _ = await _joint(db_session)
    events = TeamEventService(db_session)
    await events.set_my_attendance(guest_player, guest.id, event.id, TeamEventAttendanceStatus.GOING, None, None)

    with pytest.raises(HTTPException):
        await JointTrainingService(db_session).remove_guest(guest_captain, guest.id, event.id, guest.id)
    await JointTrainingService(db_session).remove_guest(host_captain, host.id, event.id, guest.id)

    assert await events.list_events(guest_player, guest.id) == []
    roster = await events.get_attendance_roster(host_captain, host.id, event.id)
    assert guest_player.id not in {m.user_id for m in roster.going}


# -- 2, 3 --


async def _ice_day(db_session, user: User, day: date) -> tuple[WeeklyPlan, DayPlan]:
    session = TrainingSession(id=uuid.uuid4(), blocks=[])
    day_plan = DayPlan(id=uuid.uuid4(), date=day, session_type=DaySessionType.ON_ICE, training_session=session)
    plan = WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=day - timedelta(days=day.weekday()), day_plans=[day_plan])
    db_session.add(plan)
    await db_session.flush()
    return plan, day_plan


async def _load(db_session, user: User, muscle: MuscleGroup) -> float:
    row = await db_session.scalar(
        select(UserMuscleLoad).where(UserMuscleLoad.user_id == user.id, UserMuscleLoad.muscle_group == muscle)
    )
    return row.current_value if row is not None else 0.0


@pytest.mark.asyncio
async def test_taking_a_capped_charge_back_restores_the_load_exactly(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add(UserMuscleLoad(user_id=user.id, muscle_group=MuscleGroup.GLUTES, current_value=9.0, last_updated_at=now))
    _, day_plan = await _ice_day(db_session, user, now.date())
    service = IceLoadService(db_session)

    await service.charge(user.id, day_plan.training_session.id, 1.0, now, now)
    assert await _load(db_session, user, MuscleGroup.GLUTES) == pytest.approx(MAX_INTENSITY)
    # "Не был": only the 1.0 that really landed comes off, not the full 4.5.
    await service.charge(user.id, day_plan.training_session.id, 0.0, now, now)
    assert await _load(db_session, user, MuscleGroup.GLUTES) == pytest.approx(9.0)


@pytest.mark.asyncio
async def test_rebuilding_a_charged_ice_day_takes_the_charge_off(db_session) -> None:
    from app.services.schedule_service import ScheduleService

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    _, day_plan = await _ice_day(db_session, user, now.date())
    await IceLoadService(db_session).charge(user.id, day_plan.training_session.id, 1.0, now, now)
    assert await _load(db_session, user, MuscleGroup.QUADS) == pytest.approx(4.5)

    from app.models.schedule import BlockPhase

    await ScheduleService(db_session)._rebuild_day_session(
        day_plan, DaySessionType.REST, user, BlockPhase.ACCUMULATION, None,
        archetype_rotation=None, guarantee_endurance=False, guarantee_locomotion=False,
    )
    await db_session.flush()

    assert await _load(db_session, user, MuscleGroup.QUADS) == pytest.approx(0.0, abs=1e-6)
    assert (await db_session.scalars(select(IceLoadCharge).where(IceLoadCharge.user_id == user.id))).all() == []


# -- 4 --


async def _week(db_session, user: User, monday: date, kinds: list[DaySessionType], extra_on: set[int] = frozenset()):
    days = []
    for offset, kind in enumerate(kinds):
        days.append(DayPlan(id=uuid.uuid4(), date=monday + timedelta(days=offset), session_type=kind, training_session=TrainingSession(blocks=[])))
        if offset in extra_on:
            days.append(
                DayPlan(
                    id=uuid.uuid4(), date=monday + timedelta(days=offset), session_type=DaySessionType.OFF_ICE,
                    is_extra=True, time_of_day="morning", training_session=TrainingSession(blocks=[]),
                )
            )
    db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=monday, day_plans=days))
    await db_session.flush()


MONDAY = date(2026, 3, 9)
ICE, GYM, REST, GAME = DaySessionType.ON_ICE, DaySessionType.OFF_ICE, DaySessionType.REST, DaySessionType.GAME


@pytest.mark.asyncio
async def test_template_targets_skip_the_extra_gym_and_count_games_as_reports(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    await _week(db_session, user, MONDAY, [ICE, REST, GYM, REST, REST, GAME, REST], extra_on={0})

    tasks = {t.type: t for t in await CoachTaskService(db_session).list_for_week(user, today=MONDAY)}

    assert tasks["complete_trainings"].target == 2  # ice + gym, not the extra gym nor the game
    assert tasks["ice_reports"].target == 2  # the ice and the game


@pytest.mark.asyncio
async def test_ai_tasks_replace_templates_and_fit_the_plan(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    await _week(db_session, user, MONDAY, [ICE, REST, GYM, REST, GYM, REST, REST])
    service = CoachTaskService(db_session)
    assert len(await service.list_for_week(user, today=MONDAY)) == 3  # templates

    reply = (
        '[{"type": "complete_trainings", "count": 7}, {"type": "days_in_a_row", "count": 3},'
        ' {"type": "ice_focus", "count": 5}]'
    )
    assert await service.save_ai_reply(user.id, MONDAY, reply) == 3
    tasks = {t.type: t for t in await service.list_for_week(user, today=MONDAY)}

    assert all(t.source == "coach" for t in tasks.values())
    assert tasks["complete_trainings"].target == 3  # cut to the plan
    assert tasks["ice_focus"].target == 1
    assert "days_in_a_row" not in tasks  # no two training days in a row this week


@pytest.mark.asyncio
async def test_claim_is_atomic(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    service = CoachTaskService(db_session)
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    await service.save_specs(user.id, monday, [CoachTaskSpec(CoachTaskType.NO_MISSED_DAY)], "template")
    task = (await service.list_for_week(user))[0]
    from app.models.coach_task import WeeklyCoachTask
    from sqlalchemy import update

    # Someone else's request claimed it between the read and the update.
    original_read = service._read

    async def read_then_race(*args, **kwargs):
        read = await original_read(*args, **kwargs)
        await db_session.execute(
            update(WeeklyCoachTask).where(WeeklyCoachTask.id == task.id).values(claimed_at=datetime.now(timezone.utc))
        )
        return read.model_copy(update={"done": True})

    service._read = read_then_race
    xp_before = user.xp
    with pytest.raises(HTTPException):
        await service.claim(user, task.id)
    await db_session.refresh(user)
    assert user.xp == xp_before


# -- 5 --


@pytest.mark.asyncio
async def test_guest_player_gets_the_team_training_bonus(db_session) -> None:
    _, _, _, _, guest_player, _, event, _ = await _joint(db_session)
    assert await TeamEventService(db_session).claim_team_training_reward(guest_player, event.id, None) is True


@pytest.mark.asyncio
async def test_other_teams_reasons_are_hidden_in_the_roster(db_session) -> None:
    host_captain, host_player, host, _, guest_player, guest, event, _ = await _joint(db_session)
    events = TeamEventService(db_session)
    await events.set_my_attendance(
        host_player, host.id, event.id, TeamEventAttendanceStatus.NOT_GOING, TeamEventAbsenceReason.WORK, "смена"
    )
    await events.set_my_attendance(
        guest_player, guest.id, event.id, TeamEventAttendanceStatus.NOT_GOING, TeamEventAbsenceReason.WORK, "учёба"
    )

    host_view = {m.user_id: m for m in (await events.get_attendance_roster(host_captain, host.id, event.id)).not_going}
    guest_view = {m.user_id: m for m in (await events.get_attendance_roster(guest_player, guest.id, event.id)).not_going}

    assert host_view[host_player.id].reason_note == "смена"
    assert host_view[guest_player.id].reason is None and host_view[guest_player.id].reason_note is None
    assert guest_view[guest_player.id].reason_note == "учёба"
    assert guest_view[host_player.id].reason_note is None


@pytest.mark.asyncio
async def test_leaving_takes_guests_out_of_the_lines(db_session) -> None:
    host_captain, host_player, host, guest_captain, guest_player, guest, event, _ = await _joint(db_session)
    events = TeamEventService(db_session)
    group = await events.create_lineup_group(host_captain, host.id, event.id, "Белые", None)
    await events.assign_player(host_captain, host.id, event.id, guest_player.id, group.id)
    await events.assign_player(host_captain, host.id, event.id, host_player.id, group.id)

    await JointTrainingService(db_session).leave(guest_captain, guest.id, event.id)

    read = await events.update_lineup_group(host_captain, host.id, event.id, group.id, "Белые", None)
    assert [p.user_id for p in read.players] == [host_player.id]


@pytest.mark.asyncio
async def test_declining_an_accepted_slot_leaves_its_trainings_ahead(db_session) -> None:
    host_captain, _, host = await _team(db_session, "Хозяева")
    guest_captain, guest_player, guest = await _team(db_session, "Гости")
    template = TeamIceScheduleTemplate(team_id=host.id, weekday=_future(4).weekday(), start_time=_future(4).time())
    db_session.add(template)
    await db_session.flush()
    joint = JointTrainingService(db_session)
    await joint.invite_to_template(host_captain, host.id, template.id, guest.id)
    invitation = next(i for i in await joint.list_incoming(guest_captain, guest.id) if i.kind == "slot")
    await joint.answer(guest_captain, guest.id, invitation.id, accept=True)
    from app.services.team_event_scheduler import _stamp_template

    await _stamp_template(db_session, template, datetime.now(timezone.utc))
    await db_session.flush()
    assert await TeamEventService(db_session).list_events(guest_player, guest.id)

    await joint.answer(guest_captain, guest.id, invitation.id, accept=False)

    assert await TeamEventService(db_session).list_events(guest_player, guest.id) == []


@pytest.mark.asyncio
async def test_nudge_reaches_the_guest_players(db_session, monkeypatch) -> None:
    host_captain, _, host, _, guest_player, _, event, _ = await _joint(db_session)
    db_session.add(PushSubscription(user_id=guest_player.id, endpoint="https://push.example/x", p256dh_key="k", auth_key="a"))
    await db_session.flush()
    sent_to: list[uuid.UUID] = []

    async def fake_send(session, subscription, title, body):
        sent_to.append(subscription.user_id)
        return True

    monkeypatch.setattr(team_event_service, "send_push", fake_send)
    await TeamEventService(db_session).send_nudge(host_captain, host.id, event.id)

    assert guest_player.id in sent_to


# -- 7 --


@pytest.mark.asyncio
async def test_failed_follow_up_keeps_the_coach_reply(db_session, monkeypatch) -> None:
    from app.core.config import Settings
    from app.models.coach_chat import CoachChatRole
    from app.services.coach_chat_service import CoachChatService, ZaiReply

    user = _make_user(has_premium=True)
    db_session.add(user)
    await db_session.flush()
    calls = {"n": 0}

    async def fake_call(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return ZaiReply(text="Могу записать ограничение на колено. Записать?")
        raise RuntimeError("z.ai is down")

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: Settings(zai_api_key="test-key"))
    monkeypatch.setattr(coach_chat_service, "_call_zai", fake_call)

    reply = await CoachChatService(db_session).send_message(user, "Колено болит")

    assert reply.role == CoachChatRole.ASSISTANT
    assert "Записать?" in reply.content
    assert calls["n"] == 2


# -- 8 --


def test_default_offseason_is_not_a_switch() -> None:
    march = date(2026, 3, 10)
    season_start = date(2025, 9, 1)
    user = _make_user(season_period=SeasonPeriod.OFFSEASON)
    user.created_at = datetime(2025, 9, 1, tzinfo=timezone.utc)
    assert summary_available(user, march, season_start)[0] is False
    user.season_period_changed_at = datetime(2026, 2, 20, tzinfo=timezone.utc)
    assert summary_available(user, march, season_start)[0] is True
    # Too few trainings this season -- no card even in May.
    assert summary_available(user, date(2026, 5, 10), season_start, completed_days=3)[0] is False


@pytest.mark.asyncio
async def test_stable_line_only_from_played_games_with_a_published_lineup(db_session) -> None:
    captain = _make_user(last_name="А")
    p1, p2 = _make_user(last_name="Б"), _make_user(last_name="В")
    db_session.add_all([captain, p1, p2])
    await db_session.flush()
    teams = TeamService(db_session)
    team_read = await teams.create_team(captain, "Тройка")
    for p in (p1, p2):
        request = await teams.join_by_code(p, team_read.invite_code)
        await teams.approve_request(captain, request.id)
    team = await teams._get_team_or_404(team_read.id)
    events = TeamEventService(db_session)
    start = date.today() - timedelta(days=60)

    games = []
    for game_no in range(3):
        kind = TeamEventType.TRAINING if game_no == 2 else TeamEventType.GAME
        game = await events.create_event(captain, team.id, kind, _future(1 + game_no), "Соперник" if kind == TeamEventType.GAME else None)
        line = await events.create_lineup_group(captain, team.id, game.id, "1 звено", None)
        for user, slot in ((captain, "LW"), (p1, "C"), (p2, "RW")):
            await events.assign_player(captain, team.id, game.id, user.id, line.id, slot)
        games.append(await events._events.get_event(game.id))

    # Two future games and a training: none of it went on the ice yet.
    assert await team_most_stable_line(db_session, team, start) is None
    for game in games:
        game.starts_at = datetime.now(timezone.utc) - timedelta(days=10)
    await db_session.flush()
    assert await team_most_stable_line(db_session, team, start) is None  # lineups unpublished
    for game in games:
        game.lineup_status = TeamEventPublishStatus.PUBLISHED
    await db_session.flush()
    assert await team_most_stable_line(db_session, team, start) == ["А", "Б", "В"]  # the two games


# -- 9 --


@pytest.mark.asyncio
async def test_unfinished_extra_gym_does_not_break_the_streak(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    today = utc_today()
    middle = today - timedelta(days=1)
    main = DayPlan(
        id=uuid.uuid4(), date=middle, session_type=REST, training_session=None,
    )
    extra = DayPlan(
        id=uuid.uuid4(), date=middle, session_type=GYM, is_extra=True, time_of_day="morning",
        training_session=TrainingSession(blocks=[]),
    )
    db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=middle - timedelta(days=middle.weekday()), day_plans=[main, extra]))
    await db_session.flush()

    assert await has_missed_training_day(db_session, user.id, today - timedelta(days=2), today) is False


# -- 12 --


@pytest.mark.asyncio
async def test_shadow_check_failure_does_not_poison_the_transaction(db_session, monkeypatch) -> None:
    from sqlalchemy import text

    from app.services import week_load_service

    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    async def broken(session, user_id, now=None):
        await session.execute(text("SELECT * FROM no_such_table"))

    monkeypatch.setattr(week_load_service, "evaluate_week_after_ice", broken)
    await shadow_check(db_session, user.id)

    # The outer transaction still works.
    assert (await db_session.execute(text("SELECT 1"))).scalar() == 1


@pytest.mark.asyncio
async def test_shadow_dates_ice_by_when_it_ended(db_session) -> None:
    from app.services.week_load_service import _dose_events

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    _, day_plan = await _ice_day(db_session, user, (now - timedelta(days=5)).date())
    # A report sent now about ice five days ago.
    await IceLoadService(db_session).charge(user.id, day_plan.training_session.id, 1.0, now - timedelta(days=5), now)

    events = await _dose_events(db_session, user.id, now - timedelta(days=28))
    assert events and all(at < now - timedelta(days=4) for at, _, _ in events)


# -- the small fixes after the demo (2026-10-10) --


@pytest.mark.asyncio
async def test_no_nudge_once_attendance_is_closed(db_session) -> None:
    captain, _, team = await _team(db_session, "Напоминания")
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.GAME, _future(), "Соперник")
    row = await events._events.get_event(event.id)
    row.starts_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await events.send_nudge(captain, team.id, event.id)
    assert exc.value.status_code == 409


# -- the second review round (2026-10-10) --


def test_the_weeks_focus_task_steers_the_focus_after_the_coach() -> None:
    from app.core.ice_focus import FOCUS_BY_ID, pick_focus_with_priorities

    task_focus = "skate_stops"
    focus, reason = pick_focus_with_priorities(3, {}, ["skating"], None, None, ["Мобильность"], task_focus)
    assert focus.id == task_focus and reason == "Задание тренера на эту неделю"
    # The coach's own theme still comes first.
    focus, _ = pick_focus_with_priorities(3, {}, None, ["puck_protect"], "20.10", [], task_focus)
    assert focus.id == "puck_protect"
    # An unknown id is ignored.
    focus, reason = pick_focus_with_priorities(3, {}, None, None, None, [], "made_up")
    assert focus.id in FOCUS_BY_ID and reason != "Задание тренера на эту неделю"


@pytest.mark.asyncio
async def test_ice_focus_service_uses_the_unclaimed_focus_task(db_session) -> None:
    from app.services.ice_focus_service import IceFocusService

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    day = utc_today()
    _, day_plan = await _ice_day(db_session, user, day)
    await CoachTaskService(db_session).save_specs(
        user.id, day - timedelta(days=day.weekday()), [CoachTaskSpec(CoachTaskType.ICE_FOCUS, 1, "skate_stops")], "coach"
    )

    focus = await IceFocusService(db_session).focus_for_session(user, day_plan.training_session.id)

    assert focus.id == "skate_stops"


@pytest.mark.asyncio
async def test_ice_focus_target_counts_ice_days_not_games(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    await _week(db_session, user, MONDAY, [ICE, REST, GYM, REST, REST, GAME, REST])
    service = CoachTaskService(db_session)
    await service.save_ai_reply(user.id, MONDAY, '[{"type": "ice_focus", "count": 3}, {"type": "ice_reports", "count": 3}]')

    tasks = {t.type: t for t in await service.list_for_week(user, today=MONDAY)}

    assert tasks["ice_focus"].target == 1  # one ice day; the game has no focus
    assert tasks["ice_reports"].target == 2  # the ice and the game


@pytest.mark.asyncio
async def test_training_party_overwriting_a_charged_ice_day_takes_the_charge_off(db_session) -> None:
    from app.services.schedule_service import ScheduleService

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    _, day_plan = await _ice_day(db_session, user, now.date())
    await IceLoadService(db_session).charge(user.id, day_plan.training_session.id, 1.0, now, now)
    await ScheduleService(db_session).replace_day_plan_content(day_plan, [], user)

    assert day_plan.session_type == DaySessionType.OFF_ICE
    assert await _load(db_session, user, MuscleGroup.QUADS) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.asyncio
async def test_no_leaving_or_removing_once_the_training_started(db_session) -> None:
    host_captain, _, host, guest_captain, _, guest, event, _ = await _joint(db_session)
    row = await TeamEventService(db_session)._events.get_event(event.id)
    row.starts_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.flush()
    joint = JointTrainingService(db_session)

    with pytest.raises(HTTPException) as exc:
        await joint.leave(guest_captain, guest.id, event.id)
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        await joint.remove_guest(host_captain, host.id, event.id, guest.id)
    assert exc.value.status_code == 409
