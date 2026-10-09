"""The team card (2026-10-09): the team in the style of the player card --
rating, place in its league and city, the season's games and goals (from
the scores the captain enters), training attendance and three leaders.

Open to any signed-in player, like the cross-team leaderboard: a player
card shows its team, and a tap on it lands here.
"""
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import leagues
from app.models.team import Team, TeamMembership
from app.models.team_event import (
    TeamEvent,
    TeamEventAttendance,
    TeamEventAttendanceStatus,
    TeamEventStatus,
    TeamEventType,
)
from app.models.user import User
from app.repositories.progress_repository import ProgressRepository
from app.schemas.team import TeamCardLeaderRead, TeamCardRead
from app.services.game_stats_service import GameStatsService, local_today, season_bounds
from app.services.stat_service import get_effective_value
from app.services.team_rating_service import TeamRatingService


def _streak(results: list[str]) -> str | None:
    """The current run of the same result, newest last: "В3", "П1", "Н2"."""
    if not results:
        return None
    last = results[-1]
    run = 0
    for result in reversed(results):
        if result != last:
            break
        run += 1
    return f"{last}{run}"


class TeamCardService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_card(self, viewer: User, team_id: uuid.UUID) -> TeamCardRead:
        team = await self._session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        members = list(
            (
                await self._session.scalars(
                    select(User)
                    .join(TeamMembership, TeamMembership.user_id == User.id)
                    .where(TeamMembership.team_id == team.id)
                )
            ).all()
        )
        start, end, label = season_bounds(local_today(viewer))
        season_start = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        games = (
            await self._session.scalars(
                select(TeamEvent)
                .where(
                    TeamEvent.team_id == team.id,
                    TeamEvent.event_type == TeamEventType.GAME,
                    TeamEvent.status != TeamEventStatus.CANCELLED,
                    TeamEvent.starts_at >= season_start,
                    TeamEvent.starts_at < now,
                    TeamEvent.our_score.is_not(None),
                    TeamEvent.opponent_score.is_not(None),
                )
                .order_by(TeamEvent.starts_at)
            )
        ).all()
        results = [
            "В" if g.our_score > g.opponent_score else "П" if g.our_score < g.opponent_score else "Н"
            for g in games
        ]

        score = await TeamRatingService(self._session).compute_team_score(team)
        players = await GameStatsService(self._session).season_player_stats(team, viewer, "season")
        member_ids = {m.id for m in members}
        is_member = viewer.id in member_ids

        return TeamCardRead(
            id=team.id,
            name=team.name,
            logo_url=team.logo_url,
            city=team.city,
            league_name=leagues.league_display_name(team.league_code, team.league_other_name),
            division_name=leagues.division_display_name(team.league_code, team.division_code),
            member_count=len(members),
            rating=await self._overall_rating(members),
            league_place=score.league_place,
            league_team_count=score.league_team_count,
            season_label=label,
            games=len(games),
            wins=results.count("В"),
            draws=results.count("Н"),
            losses=results.count("П"),
            goals_for=sum(g.our_score for g in games),
            goals_against=sum(g.opponent_score for g in games),
            attendance_percent=await self._attendance_percent(team, len(members), season_start, now),
            streak=_streak(results),
            leaders=self._leaders(members, players),
            is_member=is_member,
            is_captain=team.owner_id == viewer.id,
        )

    async def _overall_rating(self, members: list[User]) -> int | None:
        """The average of the members' card "ОБЩИЙ" (each one the mean of
        their six stats) -- the same number the player cards show."""
        if not members:
            return None
        stats = await ProgressRepository(self._session).list_stats_for_users([m.id for m in members])
        now = datetime.now(timezone.utc)
        by_user: dict[uuid.UUID, list[float]] = defaultdict(list)
        for stat in stats:
            by_user[stat.user_id].append(get_effective_value(stat, now))
        overalls = [sum(values) / len(values) for values in by_user.values() if values]
        if not overalls:
            return None
        return round(sum(overalls) / len(overalls))

    async def _attendance_percent(
        self, team: Team, member_count: int, season_start: datetime, now: datetime
    ) -> int | None:
        """Share of "иду" marks over the season's past team trainings, per
        current member -- a mark, not a check-in, but the closest signal
        the app has. None until there was a training."""
        training_ids = (
            await self._session.scalars(
                select(TeamEvent.id).where(
                    TeamEvent.team_id == team.id,
                    TeamEvent.event_type == TeamEventType.TRAINING,
                    TeamEvent.status != TeamEventStatus.CANCELLED,
                    TeamEvent.starts_at >= season_start,
                    TeamEvent.starts_at < now,
                )
            )
        ).all()
        if not training_ids or member_count == 0:
            return None
        going = await self._session.scalar(
            select(func.count(TeamEventAttendance.id))
            .join(TeamMembership, TeamMembership.user_id == TeamEventAttendance.user_id)
            .where(
                TeamMembership.team_id == team.id,
                TeamEventAttendance.team_event_id.in_(training_ids),
                TeamEventAttendance.status == TeamEventAttendanceStatus.GOING,
            )
        )
        return min(100, round(100 * (going or 0) / (len(training_ids) * member_count)))

    @staticmethod
    def _leaders(members: list[User], players) -> list[TeamCardLeaderRead]:
        def name(user_id: uuid.UUID, first: str, last: str) -> str:
            return last or first

        leaders: list[TeamCardLeaderRead] = []
        top_points = max(players, key=lambda p: (p.points, p.goals), default=None)
        if top_points is not None and top_points.points > 0:
            leaders.append(
                TeamCardLeaderRead(
                    title="Очки",
                    user_id=top_points.user_id,
                    name=name(top_points.user_id, top_points.first_name, top_points.last_name),
                    value=f"{top_points.points} ({top_points.goals}+{top_points.assists})",
                )
            )
        top_goals = max(players, key=lambda p: (p.goals, p.points), default=None)
        if top_goals is not None and top_goals.goals > 0:
            leaders.append(
                TeamCardLeaderRead(
                    title="Голы",
                    user_id=top_goals.user_id,
                    name=name(top_goals.user_id, top_goals.first_name, top_goals.last_name),
                    value=str(top_goals.goals),
                )
            )
        top_level = max(members, key=lambda m: (m.level, m.xp), default=None)
        if top_level is not None:
            leaders.append(
                TeamCardLeaderRead(
                    title="Уровень",
                    user_id=top_level.id,
                    name=name(top_level.id, top_level.first_name, top_level.last_name),
                    value=f"Ур. {top_level.level}",
                )
            )
        return leaders
