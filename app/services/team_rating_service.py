import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import DayPlan, SessionBlock, TrainingSession, WeeklyPlan
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.schemas.team import TeamScoreRead
from app.services.streak_service import TRAINING_SESSION_TYPES

# Teams below this size never appear in the cross-team ranking (their own
# team_score is still computable and shown on the team's own page).
MIN_MEMBERS_FOR_LEADERBOARD = 8

ACTIVITY_BONUS_WEIGHT = 0.15
ACTIVITY_TARGET_TRAININGS_PER_WEEK = 4.0
ACTIVITY_WINDOW_DAYS = 7


def _activity_bonus(avg_trainings_per_member_per_week: float) -> float:
    return (
        min(avg_trainings_per_member_per_week / ACTIVITY_TARGET_TRAININGS_PER_WEEK, 1.0)
        * ACTIVITY_BONUS_WEIGHT
    )


class TeamRatingService:
    """team_score = sum(member.xp) * (1 + activity_bonus), never persisted --
    always recomputed from User.xp and completed SessionBlocks. Deliberately
    doesn't touch age/rating_excess (see ProgressService.get_rating_excess):
    a team with unassessed or age-less members still gets a score.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def compute_team_score(self, team: Team) -> TeamScoreRead:
        sum_xp, member_count = await self._xp_and_member_count(team.id)
        completed_trainings = await self._completed_trainings_count(team.id)
        return self._to_score(team.id, team.name, sum_xp, member_count, completed_trainings)

    async def get_team_rankings(self, limit: int, offset: int) -> list[TeamScoreRead]:
        """Cross-team leaderboard: every team with >= MIN_MEMBERS_FOR_LEADERBOARD
        members, ranked by team_score descending. Both aggregates (xp sum and
        completed-trainings count) are computed with one GROUP BY query each,
        across all teams at once -- never one query per team.
        """
        xp_by_team = await self._xp_and_member_count_by_team()
        trainings_by_team = await self._completed_trainings_count_by_team()

        scores = [
            self._to_score(team_id, name, sum_xp, member_count, trainings_by_team.get(team_id, 0))
            for team_id, (name, sum_xp, member_count) in xp_by_team.items()
            if member_count >= MIN_MEMBERS_FOR_LEADERBOARD
        ]
        scores.sort(key=lambda score: score.team_score, reverse=True)
        return scores[offset : offset + limit]

    @staticmethod
    def _to_score(
        team_id: uuid.UUID, team_name: str, sum_xp: int, member_count: int, completed_trainings: int
    ) -> TeamScoreRead:
        # member_count is 0 only in theory -- a team always keeps its captain
        # as a member (TeamService.create_team, leave_team 409s the captain)
        # -- guarded anyway rather than trusting that invariant here too.
        avg_trainings = completed_trainings / member_count if member_count > 0 else 0.0
        bonus = _activity_bonus(avg_trainings)
        return TeamScoreRead(
            team_id=team_id,
            team_name=team_name,
            team_score=round(sum_xp * (1 + bonus), 1),
            member_count=member_count,
            sum_xp=sum_xp,
            avg_trainings_per_member_per_week=round(avg_trainings, 2),
            activity_bonus=round(bonus, 4),
        )

    async def _xp_and_member_count(self, team_id: uuid.UUID) -> tuple[int, int]:
        result = await self._session.execute(
            select(func.coalesce(func.sum(User.xp), 0), func.count(User.id))
            .select_from(TeamMembership)
            .join(User, User.id == TeamMembership.user_id)
            .where(TeamMembership.team_id == team_id)
        )
        return result.one()

    async def _xp_and_member_count_by_team(self) -> dict[uuid.UUID, tuple[str, int, int]]:
        result = await self._session.execute(
            select(Team.id, Team.name, func.coalesce(func.sum(User.xp), 0), func.count(User.id))
            .select_from(Team)
            .join(TeamMembership, TeamMembership.team_id == Team.id)
            .join(User, User.id == TeamMembership.user_id)
            .group_by(Team.id, Team.name)
        )
        return {row[0]: (row[1], row[2], row[3]) for row in result.all()}

    def _completed_trainings_exists(self):
        # Correlates to the enclosing query's DayPlan via day_plan_id ==
        # DayPlan.id -- same EXISTS shape as streak_service.has_missed_training_day,
        # reused here rather than re-deriving what "a training was completed"
        # means a second time.
        return (
            select(SessionBlock.id)
            .join(TrainingSession, SessionBlock.session_id == TrainingSession.id)
            .where(
                TrainingSession.day_plan_id == DayPlan.id,
                SessionBlock.completed_at.is_not(None),
            )
            .exists()
        )

    async def _completed_trainings_count(self, team_id: uuid.UUID) -> int:
        since = date.today() - timedelta(days=ACTIVITY_WINDOW_DAYS - 1)
        result = await self._session.execute(
            select(func.count(DayPlan.id))
            .select_from(DayPlan)
            .join(WeeklyPlan, DayPlan.weekly_plan_id == WeeklyPlan.id)
            .join(TeamMembership, TeamMembership.user_id == WeeklyPlan.user_id)
            .where(
                TeamMembership.team_id == team_id,
                DayPlan.date >= since,
                DayPlan.session_type.in_(TRAINING_SESSION_TYPES),
                self._completed_trainings_exists(),
            )
        )
        return result.scalar_one()

    async def _completed_trainings_count_by_team(self) -> dict[uuid.UUID, int]:
        since = date.today() - timedelta(days=ACTIVITY_WINDOW_DAYS - 1)
        result = await self._session.execute(
            select(TeamMembership.team_id, func.count(DayPlan.id))
            .select_from(DayPlan)
            .join(WeeklyPlan, DayPlan.weekly_plan_id == WeeklyPlan.id)
            .join(TeamMembership, TeamMembership.user_id == WeeklyPlan.user_id)
            .where(
                DayPlan.date >= since,
                DayPlan.session_type.in_(TRAINING_SESSION_TYPES),
                self._completed_trainings_exists(),
            )
            .group_by(TeamMembership.team_id)
        )
        return {row[0]: row[1] for row in result.all()}
