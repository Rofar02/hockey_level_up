"""«Мой сезон» and the team's season (2026-10-09, release plan step 10)."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.team_event import TeamEventPublishStatus, TeamEventType
from app.models.user import SeasonPeriod, User
from app.services.season_summary_service import SeasonSummaryService, summary_available, team_most_stable_line
from app.services.team_event_service import TeamEventService
from app.services.team_service import TeamService

SEASON_START = date(2025, 9, 1)


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(id=uuid.uuid4(), username=f"ss_{unique}", email=f"ss_{unique}@example.com", password_hash="x", timezone="UTC")
    defaults.update(overrides)
    return User(**defaults)


def _user_since(days_ago: int, period: SeasonPeriod) -> User:
    user = _make_user(season_period=period)
    user.created_at = datetime(2026, 5, 10, tzinfo=timezone.utc) - timedelta(days=days_ago)
    return user


def test_card_opens_in_may_or_with_offseason_in_spring_after_six_weeks() -> None:
    may = date(2026, 5, 10)
    march = date(2026, 3, 10)
    october = date(2025, 10, 10)
    assert summary_available(_user_since(100, SeasonPeriod.SEASON), may, SEASON_START)[0] is True
    assert summary_available(_user_since(10, SeasonPeriod.SEASON), may, SEASON_START)[0] is False
    off = _user_since(100, SeasonPeriod.OFFSEASON)
    off.created_at = datetime(2025, 9, 1, tzinfo=timezone.utc)
    off.season_period_changed_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert summary_available(off, march, SEASON_START)[0] is True
    # Off-season is the default for a new account -- not enough in the autumn.
    assert summary_available(off, october, SEASON_START)[0] is False


@pytest.mark.asyncio
async def test_preview_builds_the_card_with_linemate_and_team(db_session) -> None:
    me = _make_user(last_name="Гредзен", level=7)
    mate = _make_user(first_name="Иван", last_name="Соколов")
    db_session.add_all([me, mate])
    await db_session.flush()
    teams = TeamService(db_session)
    team = await teams.create_team(me, "Медведи")
    request = await teams.join_by_code(mate, team.invite_code)
    await teams.approve_request(me, request.id)
    events = TeamEventService(db_session)
    game = await events.create_event(me, team.id, TeamEventType.GAME, datetime.now(timezone.utc) + timedelta(days=1), "Волки")
    line = await events.create_lineup_group(me, team.id, game.id, "1 звено", None)
    await events.assign_player(me, team.id, game.id, me.id, line.id, "LW")
    await events.assign_player(me, team.id, game.id, mate.id, line.id, "C")
    # Lines count from games already played with a published lineup.
    played = await events._events.get_event(game.id)
    played.starts_at = datetime.now(timezone.utc) - timedelta(days=1)
    played.lineup_status = TeamEventPublishStatus.PUBLISHED
    await db_session.flush()

    summary = await SeasonSummaryService(db_session).summary(me, preview=True)

    assert summary.frequent_linemate == "Иван Соколов"
    assert summary.team is not None and summary.team.name == "Медведи"
    assert summary.level == 7


@pytest.mark.asyncio
async def test_not_available_without_preview_returns_only_reason(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    summary = await SeasonSummaryService(db_session).summary(user)
    assert summary.available is False
    assert summary.reason is not None


@pytest.mark.asyncio
async def test_team_most_stable_line_needs_the_same_trio_twice(db_session) -> None:
    captain = _make_user(last_name="А")
    p1, p2 = _make_user(last_name="Б"), _make_user(last_name="В")
    db_session.add_all([captain, p1, p2])
    await db_session.flush()
    teams = TeamService(db_session)
    team_read = await teams.create_team(captain, "Тройка")
    for p in (p1, p2):
        request = await teams.join_by_code(p, team_read.invite_code)
        await teams.approve_request(captain, request.id)
    events = TeamEventService(db_session)
    team = await teams._get_team_or_404(team_read.id)
    start = date.today() - timedelta(days=30)

    for game_no in range(2):
        game = await events.create_event(
            captain, team.id, TeamEventType.GAME, datetime.now(timezone.utc) + timedelta(days=1 + game_no), "Соперник"
        )
        line = await events.create_lineup_group(captain, team.id, game.id, "1 звено", None)
        for user, slot in ((captain, "LW"), (p1, "C"), (p2, "RW")):
            await events.assign_player(captain, team.id, game.id, user.id, line.id, slot)
        played = await events._events.get_event(game.id)
        played.starts_at = datetime.now(timezone.utc) - timedelta(days=2 + game_no)
        played.lineup_status = TeamEventPublishStatus.PUBLISHED
        await db_session.flush()
        if game_no == 0:
            assert await team_most_stable_line(db_session, team, start) is None

    assert await team_most_stable_line(db_session, team, start) == ["А", "Б", "В"]
