"""Game numbers from the players' own game reports (2026-10-08): the
player's season in their profile, and the captain's table of the team.

A season runs September 1 - August 31 (a hockey season). The team table
only counts this team's scheduled games (a DayPlan taken over by one of the
team's GAME events) -- a game a player put in their own plan (another team,
a tournament) is in their own season, not in the coach's table. The
self-rating and "над чем поработать" reach the coach only from games the
player chose to share them for.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.push_subscription import PushSubscription
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.team import Team, TeamMembership
from app.models.team_event import TeamEvent, TeamEventStatus, TeamEventType
from app.models.training_diary import GameResult, TrainingDiaryEntry
from app.models.user import User
from app.schemas.game_stats import SeasonGame, SeasonRead, TeamPlayerStats, TeamStatsRead, TeamStatsReminderRead
from app.services.push_service import send_push

SEASON_START_MONTH = 9
SEASON_GAMES_SHOWN = 20
REMINDER_MIN_INTERVAL = timedelta(hours=1)


def season_bounds(today: date) -> tuple[date, date, str]:
    start_year = today.year if today.month >= SEASON_START_MONTH else today.year - 1
    start = date(start_year, SEASON_START_MONTH, 1)
    end = date(start_year + 1, SEASON_START_MONTH, 1) - timedelta(days=1)
    return start, end, f"{start_year}/{str(start_year + 1)[-2:]}"


def _local_today(user: User) -> date:
    return datetime.now(ZoneInfo(user.timezone or "UTC")).date()


class GameStatsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def my_season(self, user: User) -> SeasonRead:
        start, end, label = season_bounds(_local_today(user))
        rows = (
            await self._session.execute(
                select(DayPlan.date, DayPlan.id, TrainingDiaryEntry)
                .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
                .join(TrainingSession, TrainingSession.day_plan_id == DayPlan.id)
                .join(TrainingDiaryEntry, TrainingDiaryEntry.training_session_id == TrainingSession.id)
                .where(
                    WeeklyPlan.user_id == user.id,
                    DayPlan.session_type == DaySessionType.GAME,
                    DayPlan.date.between(start, end),
                    TrainingDiaryEntry.game_result.isnot(None),
                )
                .order_by(DayPlan.date)
            )
        ).all()
        entries = [entry for _, _, entry in rows]
        ratings = [e.self_rating for e in entries if e.self_rating is not None]
        goals = sum(e.goals or 0 for e in entries)
        assists = sum(e.assists or 0 for e in entries)
        return SeasonRead(
            label=label,
            start=start,
            end=end,
            games=len(entries),
            wins=sum(e.game_result == GameResult.WIN for e in entries),
            draws=sum(e.game_result == GameResult.DRAW for e in entries),
            losses=sum(e.game_result == GameResult.LOSS for e in entries),
            goals=goals,
            assists=assists,
            points=goals + assists,
            shots=sum(e.shots or 0 for e in entries),
            avg_self_rating=round(sum(ratings) / len(ratings), 1) if ratings else None,
            recent_games=[
                SeasonGame(
                    date=day,
                    day_plan_id=day_plan_id,
                    result=entry.game_result,
                    goals=entry.goals,
                    assists=entry.assists,
                    shots=entry.shots,
                    self_rating=entry.self_rating,
                )
                for day, day_plan_id, entry in rows[-SEASON_GAMES_SHOWN:]
            ],
        )

    async def team_stats(self, user: User, team_id: uuid.UUID, scope: str) -> TeamStatsRead:
        team = await self._captains_team(user, team_id)
        start, end, label = season_bounds(_local_today(user))
        now = datetime.now(timezone.utc)
        games = (
            await self._session.scalars(
                select(TeamEvent)
                .where(
                    TeamEvent.team_id == team.id,
                    TeamEvent.event_type == TeamEventType.GAME,
                    TeamEvent.status != TeamEventStatus.CANCELLED,
                    TeamEvent.starts_at < now,
                    TeamEvent.starts_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
                )
                .order_by(TeamEvent.starts_at)
            )
        ).all()
        last_game = games[-1] if games else None
        counted = [last_game] if scope == "last_game" and last_game is not None else list(games)
        if scope == "last_game" and last_game is None:
            counted = []

        members = (
            await self._session.scalars(
                select(User)
                .join(TeamMembership, TeamMembership.user_id == User.id)
                .where(TeamMembership.team_id == team.id)
                .order_by(User.jersey_number.nulls_last(), User.last_name)
            )
        ).all()
        # (user_id, event_id) -> that player's entry (None = played, no entry).
        rows = (
            await self._session.execute(
                select(WeeklyPlan.user_id, DayPlan.team_event_id, TrainingDiaryEntry)
                .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
                .join(TrainingSession, TrainingSession.day_plan_id == DayPlan.id, isouter=True)
                .join(
                    TrainingDiaryEntry,
                    TrainingDiaryEntry.training_session_id == TrainingSession.id,
                    isouter=True,
                )
                .where(DayPlan.team_event_id.in_([g.id for g in counted]))
            )
        ).all()

        players = []
        for member in members:
            mine = [entry for user_id, _, entry in rows if user_id == member.id]
            reported = [e for e in mine if e is not None and e.game_result is not None]
            shared = [e for e in reported if e.share_rating_with_coach]
            ratings = [e.self_rating for e in shared if e.self_rating is not None]
            goals = sum(e.goals or 0 for e in reported)
            assists = sum(e.assists or 0 for e in reported)
            latest_shared = next((e for e in reversed(shared) if e.work_on), None)
            players.append(
                TeamPlayerStats(
                    user_id=member.id,
                    first_name=member.first_name,
                    last_name=member.last_name,
                    jersey_number=member.jersey_number,
                    games=len(reported),
                    goals=goals,
                    assists=assists,
                    points=goals + assists,
                    shots=sum(e.shots or 0 for e in reported),
                    avg_self_rating=round(sum(ratings) / len(ratings), 1) if ratings else None,
                    work_on=latest_shared.work_on if latest_shared is not None else None,
                    missing_reports=sum(e is None or e.reported_at is None for e in mine),
                )
            )
        players.sort(key=lambda p: (-p.points, -p.goals, p.jersey_number if p.jersey_number is not None else 999))
        return TeamStatsRead(
            scope=scope,
            season_label=label,
            last_game_date=last_game.starts_at.date() if last_game is not None else None,
            players=players,
        )

    async def remind_missing(self, user: User, team_id: uuid.UUID) -> TeamStatsReminderRead:
        """A push to every member with a played team game still unreported,
        at most once per REMINDER_MIN_INTERVAL per team."""
        team = await self._captains_team(user, team_id)
        now = datetime.now(timezone.utc)
        if team.stats_reminder_sent_at is not None and now - team.stats_reminder_sent_at < REMINDER_MIN_INTERVAL:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Напомнить можно раз в час"
            )
        stats = await self.team_stats(user, team_id, "season")
        targets = [p.user_id for p in stats.players if p.missing_reports > 0 and p.user_id != user.id]
        if targets:
            subscriptions = (
                await self._session.scalars(select(PushSubscription).where(PushSubscription.user_id.in_(targets)))
            ).all()
            for subscription in subscriptions:
                await send_push(
                    self._session,
                    subscription,
                    "Как сыграли?",
                    f"Тренер «{team.name}» ждёт отчёт об игре — пара тапов.",
                    url="/diary",
                )
        team.stats_reminder_sent_at = now
        await self._session.commit()
        return TeamStatsReminderRead(reminded=len(targets))

    async def _captains_team(self, user: User, team_id: uuid.UUID) -> Team:
        team = await self._session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        if team.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the team captain can do this")
        return team
