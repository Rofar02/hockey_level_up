"""Game numbers from game reports (2026-10-08): the season's bounds, the
player's own season, and the captain's team table -- only this team's
games, the self-rating only when shared, unreported games counted, captain
only, and the reminder's once-an-hour limit."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.team_event import TeamEvent, TeamEventType
from app.models.training_diary import GameResult, GameWorkOn
from app.models.user import User
from app.schemas.training_diary import DiaryReportIn
from app.services import push_service
from app.services.game_stats_service import GameStatsService, season_bounds
from app.services.team_service import TeamService
from app.services.training_diary_service import TrainingDiaryService
from tests.dates import utc_today


def test_season_runs_september_to_august() -> None:
    assert season_bounds(date(2026, 10, 8)) == (date(2026, 9, 1), date(2027, 8, 31), "2026/27")
    assert season_bounds(date(2027, 3, 1)) == (date(2026, 9, 1), date(2027, 8, 31), "2026/27")
    assert season_bounds(date(2026, 8, 31))[2] == "2025/26"


_WEEK_STARTS = (date(2000, 1, 3) + timedelta(weeks=n) for n in range(10_000))


def _user(jersey: int | None = None) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"stats_{unique}",
        email=f"stats_{unique}@example.com",
        password_hash="x",
        first_name="Иван",
        last_name=f"Игрок{unique[:3]}",
        jersey_number=jersey,
        timezone="UTC",
    )


async def _game_day(db_session, user: User, day: date, team_event_id: uuid.UUID | None = None) -> TrainingSession:
    training_session = TrainingSession(id=uuid.uuid4(), blocks=[])
    # Its own plan per day (one per user and week_start is the rule) -- the
    # stats only read DayPlan.date, not the plan's week.
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=next(_WEEK_STARTS))
    weekly_plan.day_plans.append(
        DayPlan(id=uuid.uuid4(), date=day, session_type=DaySessionType.GAME, team_event_id=team_event_id,
                training_session=training_session)
    )
    db_session.add(weekly_plan)
    await db_session.flush()
    return training_session


def _report(goals: int, assists: int, rating: int, share: bool = False, work_on=()) -> DiaryReportIn:
    return DiaryReportIn(
        game_result=GameResult.WIN, goals=goals, assists=assists, shots=goals * 3, self_rating=rating,
        work_on=list(work_on), share_rating_with_coach=share,
    )


@pytest.mark.asyncio
async def test_my_season_sums_the_reports(db_session) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()
    diary = TrainingDiaryService(db_session)
    first = await _game_day(db_session, user, utc_today() - timedelta(days=1))
    second = await _game_day(db_session, user, utc_today())
    skipped = await _game_day(db_session, user, utc_today() - timedelta(days=2))
    await diary.save_entry(user, first.id, None, _report(1, 2, 4))
    await diary.save_entry(user, second.id, None, _report(2, 0, 2))
    await diary.save_entry(user, skipped.id, None, DiaryReportIn(skipped=True))

    season = await GameStatsService(db_session).my_season(user)

    assert (season.games, season.goals, season.assists, season.points, season.shots) == (2, 3, 2, 5, 9)
    assert season.wins == 2 and season.avg_self_rating == 3.0
    assert [g.goals for g in season.recent_games] == [1, 2]  # oldest first


async def _team_setup(db_session):
    captain, player, other = _user(1), _user(17), _user(9)
    db_session.add_all([captain, player, other])
    await db_session.flush()
    teams = TeamService(db_session)
    team = await teams.create_team(captain, "Sharks")
    for member in (player, other):
        request = await teams.join_by_code(member, team.invite_code)
        await teams.approve_request(captain, request.id)
    started = datetime.now(timezone.utc) - timedelta(days=1)
    game = TeamEvent(id=uuid.uuid4(), team_id=team.id, event_type=TeamEventType.GAME, starts_at=started)
    db_session.add(game)
    await db_session.flush()
    return captain, player, other, team, game


@pytest.mark.asyncio
async def test_team_table_counts_team_games_and_respects_sharing(db_session) -> None:
    captain, player, other, team, game = await _team_setup(db_session)
    diary = TrainingDiaryService(db_session)
    day = game.starts_at.date()
    player_game = await _game_day(db_session, player, day, game.id)
    await _game_day(db_session, other, day, game.id)  # played, no report
    own_game = await _game_day(db_session, player, day - timedelta(days=1))  # not a team game
    await diary.save_entry(player, player_game.id, None, _report(1, 2, 4, share=True, work_on=[GameWorkOn.DEFENSE]))
    await diary.save_entry(player, own_game.id, None, _report(3, 3, 5))

    stats = await GameStatsService(db_session).team_stats(captain, team.id, "season")

    by_id = {p.user_id: p for p in stats.players}
    mine = by_id[player.id]
    assert (mine.games, mine.goals, mine.assists, mine.points) == (1, 1, 2, 3)
    assert mine.avg_self_rating == 4.0 and mine.work_on == ["defense"]
    assert by_id[other.id].missing_reports == 1 and by_id[other.id].games == 0
    assert stats.players[0].user_id == player.id  # most points first
    assert stats.last_game_date == day


@pytest.mark.asyncio
async def test_unshared_rating_stays_private(db_session) -> None:
    captain, player, _, team, game = await _team_setup(db_session)
    session = await _game_day(db_session, player, game.starts_at.date(), game.id)
    await TrainingDiaryService(db_session).save_entry(
        player, session.id, None, _report(0, 1, 2, share=False, work_on=[GameWorkOn.SKATING])
    )

    stats = await GameStatsService(db_session).team_stats(captain, team.id, "last_game")

    mine = next(p for p in stats.players if p.user_id == player.id)
    assert mine.assists == 1 and mine.avg_self_rating is None and mine.work_on is None


@pytest.mark.asyncio
async def test_only_the_captain_sees_the_table(db_session) -> None:
    _, player, _, team, _ = await _team_setup(db_session)
    with pytest.raises(HTTPException) as error:
        await GameStatsService(db_session).team_stats(player, team.id, "season")
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_reminder_reaches_unreported_players_once_an_hour(db_session, monkeypatch) -> None:
    sent = []

    async def _fake(*_args, **_kwargs):
        sent.append(1)
        return "ok"

    monkeypatch.setattr(push_service, "webpush_async", _fake)
    captain, player, other, team, game = await _team_setup(db_session)
    await _game_day(db_session, other, game.starts_at.date(), game.id)
    service = GameStatsService(db_session)

    result = await service.remind_missing(captain, team.id)
    assert result.reminded == 1
    with pytest.raises(HTTPException) as error:
        await service.remind_missing(captain, team.id)
    assert error.value.status_code == 429
