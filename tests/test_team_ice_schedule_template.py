"""TeamEventService ice schedule template CRUD (captain-only writes) and
the scheduler's stamping of TeamEvent rows from active templates --
idempotent, horizon-bounded, and skips slots already in the past. Same
_make_team_with_player shape as the other team_event test modules.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.team_event import TeamEventStatus, TeamEventType
from app.models.user import User
from app.services.team_event_scheduler import STAMP_WEEKS_AHEAD, _run_tick
from app.services.team_event_service import TeamEventService
from app.services.team_service import TeamService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"template_{unique}",
        email=f"template_{unique}@example.com",
        password_hash="irrelevant",
        timezone="UTC",
    )
    defaults.update(overrides)
    return User(**defaults)


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


@pytest.mark.asyncio
async def test_create_template_requires_captain(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await events.create_template(player, team.id, 1, datetime(2000, 1, 1, 19, 0).time())
    assert exc_info.value.status_code == 403

    template = await events.create_template(
        captain, team.id, 1, datetime(2000, 1, 1, 19, 0).time()
    )
    assert template.weekday == 1
    assert template.active is True


@pytest.mark.asyncio
async def test_deactivate_and_delete_template(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    template = await events.create_template(
        captain, team.id, 2, datetime(2000, 1, 1, 19, 0).time()
    )

    deactivated = await events.set_template_active(captain, team.id, template.id, False)
    assert deactivated.active is False

    with pytest.raises(HTTPException) as exc_info:
        await events.set_template_active(player, team.id, template.id, True)
    assert exc_info.value.status_code == 403

    await events.delete_template(captain, team.id, template.id)
    templates = await events.list_templates(captain, team.id)
    assert templates == []


@pytest.mark.asyncio
async def test_stamping_creates_event_on_matching_weekday(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    target_date = now.date() + timedelta(days=3)
    template = await events.create_template(captain, team.id, target_date.weekday(), (now + timedelta(hours=1)).time())

    await _run_tick(db_session, now)

    stamped = await events.list_events(captain, team.id)
    matching = [
        e for e in stamped
        if e.event_type == TeamEventType.TRAINING and e.starts_at.date() == target_date
    ]
    assert len(matching) == 1
    assert matching[0].status == TeamEventStatus.SCHEDULED


@pytest.mark.asyncio
async def test_stamping_is_idempotent_across_ticks(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    await events.create_template(captain, team.id, now.weekday(), (now + timedelta(days=7)).time())

    await _run_tick(db_session, now)
    first_count = len(await events.list_events(captain, team.id))
    await _run_tick(db_session, now + timedelta(minutes=5))
    second_count = len(await events.list_events(captain, team.id))

    assert first_count > 0
    assert first_count == second_count


@pytest.mark.asyncio
async def test_stamping_skips_inactive_template(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    template = await events.create_template(
        captain, team.id, now.weekday(), (now + timedelta(days=7)).time()
    )
    await events.set_template_active(captain, team.id, template.id, False)

    await _run_tick(db_session, now)

    assert await events.list_events(captain, team.id) == []


@pytest.mark.asyncio
async def test_stamping_never_creates_a_past_slot(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    # Today, one hour in the PAST -- must not be stamped for today, only
    # for the same weekday next week (still within the horizon).
    await events.create_template(captain, team.id, now.weekday(), (now - timedelta(hours=1)).time())

    await _run_tick(db_session, now)

    stamped = await events.list_events(captain, team.id)
    assert all(e.starts_at > now for e in stamped)
    assert all(e.starts_at.date() != now.date() for e in stamped)


@pytest.mark.asyncio
async def test_stamping_stays_within_horizon(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    await events.create_template(captain, team.id, now.weekday(), (now + timedelta(hours=1)).time())

    await _run_tick(db_session, now)

    stamped = await events.list_events(captain, team.id)
    horizon = now + timedelta(weeks=STAMP_WEEKS_AHEAD, days=1)
    assert all(e.starts_at <= horizon for e in stamped)
