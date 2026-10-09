"""«Мой сезон» (2026-10-09, release plan step 10): the season so far as a
card worth sharing -- ice days, games, gym sessions, team attendance, the
stats then and now, the best streak, the level, the most frequent
linemate and the team.

The season is the same one as on the Season screen (September 1 -- August
31), summed up over its playing part: the card shows once the player has
switched to the off-season (from SUMMARY_OFFSEASON_FROM_MONTH), or from
SUMMARY_FROM_MONTH anyway. SeasonPeriod.OFFSEASON is also the default for
a new account, so it alone doesn't open the card in the autumn. Fewer than
MIN_DAYS_IN_APP in the app -> no card: an almost empty card is a sad one.
"""
import uuid
from collections import Counter
from datetime import date, datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import TargetStat
from app.models.progress import StatHistory, TrainingStreak
from app.models.schedule import DaySessionType
from app.models.team import Team, TeamMembership
from app.models.team_event import (
    TeamEvent,
    TeamEventAttendance,
    TeamEventAttendanceStatus,
    TeamEventLineupSlot,
    TeamEventStatus,
)
from app.models.user import SeasonPeriod, User
from app.schemas.season_summary import SeasonStatChangeRead, SeasonSummaryRead
from app.services.game_stats_service import local_today, season_bounds
from app.services.progress_service import ProgressService
from app.services.streak_service import list_activity_calendar
from app.services.team_service import TeamService

SUMMARY_FROM_MONTH = 5  # May
SUMMARY_OFFSEASON_FROM_MONTH = 3  # March, once the player switched to the off-season
MIN_DAYS_IN_APP = 42


def summary_available(user: User, today: date, season_start: date) -> tuple[bool, str | None]:
    if (today - user.created_at.date()).days < MIN_DAYS_IN_APP:
        return False, "Итог сезона появится, когда наберётся хотя бы шесть недель в приложении."
    in_spring = today.year > season_start.year
    if in_spring and today.month >= SUMMARY_FROM_MONTH:
        return True, None
    if in_spring and user.season_period == SeasonPeriod.OFFSEASON and today.month >= SUMMARY_OFFSEASON_FROM_MONTH:
        return True, None
    return False, "Итог сезона появится весной — когда переключите период на «межсезонье» или с мая."


class SeasonSummaryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def summary(self, user: User, preview: bool = False) -> SeasonSummaryRead:
        today = local_today(user)
        start, end, label = season_bounds(today)
        available, reason = summary_available(user, today, start)
        if not available and not preview:
            return SeasonSummaryRead(available=False, reason=reason, season_label=label)

        days = await list_activity_calendar(self._session, user.id, start, min(today, end))
        done = [d for d in days if d.fully_completed]
        ice_days = sum(1 for d in done if d.session_type == DaySessionType.ON_ICE)
        games = sum(1 for d in days if d.session_type == DaySessionType.GAME and d.date <= today)
        gym = sum(1 for d in done if d.session_type == DaySessionType.OFF_ICE)

        stats = await self._stat_changes(user.id, start)
        overall_before = _overall([s.before for s in stats])
        overall_after = _overall([s.after for s in stats])
        best_streak = await self._session.scalar(
            select(TrainingStreak.longest_streak).where(TrainingStreak.user_id == user.id)
        )

        return SeasonSummaryRead(
            available=available,
            reason=reason,
            season_label=label,
            ice_days=ice_days,
            games=games,
            gym_sessions=gym,
            team_attendance_percent=await self._team_attendance(user.id, start, today),
            stats=stats,
            overall_before=overall_before,
            overall_after=overall_after,
            best_streak=best_streak or 0,
            level=user.level,
            frequent_linemate=await self._frequent_linemate(user.id, start),
            team=await TeamService(self._session).get_player_team_badge(user.id),
        )

    async def _stat_changes(self, user_id: uuid.UUID, start: date) -> list[SeasonStatChangeRead]:
        """Each stat at the season start (its last recorded value before it,
        else its first one in the season) and now."""
        start_at = datetime.combine(start, time.min, tzinfo=timezone.utc)
        current = {s.stat_type: s.effective_value for s in await ProgressService(self._session).list_user_stats(user_id)}
        changes = []
        for stat in TargetStat:
            if stat not in current:
                continue
            before = await self._session.scalar(
                select(StatHistory.value)
                .where(StatHistory.user_id == user_id, StatHistory.stat_type == stat, StatHistory.recorded_at < start_at)
                .order_by(StatHistory.recorded_at.desc())
                .limit(1)
            )
            if before is None:
                before = await self._session.scalar(
                    select(StatHistory.value)
                    .where(StatHistory.user_id == user_id, StatHistory.stat_type == stat)
                    .order_by(StatHistory.recorded_at)
                    .limit(1)
                )
            changes.append(
                SeasonStatChangeRead(
                    stat=stat.value,
                    before=round(before if before is not None else current[stat], 1),
                    after=round(current[stat], 1),
                )
            )
        return changes

    async def _team_attendance(self, user_id: uuid.UUID, start: date, today: date) -> int | None:
        team_id = await self._session.scalar(select(TeamMembership.team_id).where(TeamMembership.user_id == user_id))
        if team_id is None:
            return None
        start_at = datetime.combine(start, time.min, tzinfo=timezone.utc)
        event_ids = (
            await self._session.scalars(
                select(TeamEvent.id).where(
                    TeamEvent.team_id == team_id,
                    TeamEvent.status == TeamEventStatus.SCHEDULED,
                    TeamEvent.starts_at >= start_at,
                    TeamEvent.starts_at < datetime.now(timezone.utc),
                )
            )
        ).all()
        if not event_ids:
            return None
        going = await self._session.scalar(
            select(func.count(TeamEventAttendance.id)).where(
                TeamEventAttendance.user_id == user_id,
                TeamEventAttendance.team_event_id.in_(event_ids),
                TeamEventAttendance.status == TeamEventAttendanceStatus.GOING,
            )
        )
        return round(100 * (going or 0) / len(event_ids))

    async def _frequent_linemate(self, user_id: uuid.UUID, start: date) -> str | None:
        """Who the player was most often in the same line with, from the
        game lineups of the season."""
        start_at = datetime.combine(start, time.min, tzinfo=timezone.utc)
        my_groups = (
            await self._session.scalars(
                select(TeamEventLineupSlot.group_id)
                .join(TeamEvent, TeamEvent.id == TeamEventLineupSlot.team_event_id)
                .where(TeamEventLineupSlot.user_id == user_id, TeamEvent.starts_at >= start_at)
            )
        ).all()
        if not my_groups:
            return None
        partners = (
            await self._session.scalars(
                select(TeamEventLineupSlot.user_id).where(
                    TeamEventLineupSlot.group_id.in_(my_groups), TeamEventLineupSlot.user_id != user_id
                )
            )
        ).all()
        if not partners:
            return None
        partner_id, _ = Counter(partners).most_common(1)[0]
        partner = await self._session.get(User, partner_id)
        if partner is None:
            return None
        return f"{partner.first_name} {partner.last_name}".strip()


def _overall(values: list[float]) -> int | None:
    return round(sum(values) / len(values)) if values else None


async def team_most_stable_line(session: AsyncSession, team: Team, start: date) -> list[str] | None:
    """The team's most repeated line of the season: the same three
    forwards (by slot LW/C/RW) in the most games. None until a line
    repeats at least twice."""
    start_at = datetime.combine(start, time.min, tzinfo=timezone.utc)
    rows = (
        await session.execute(
            select(TeamEventLineupSlot.group_id, TeamEventLineupSlot.user_id)
            .join(TeamEvent, TeamEvent.id == TeamEventLineupSlot.team_event_id)
            .where(
                TeamEvent.team_id == team.id,
                TeamEvent.starts_at >= start_at,
                TeamEventLineupSlot.slot_position.in_(("LW", "C", "RW")),
            )
        )
    ).all()
    groups: dict[uuid.UUID, set[uuid.UUID]] = {}
    for group_id, uid in rows:
        groups.setdefault(group_id, set()).add(uid)
    trios = Counter(frozenset(members) for members in groups.values() if len(members) == 3)
    if not trios:
        return None
    trio, times = trios.most_common(1)[0]
    if times < 2:
        return None
    users = (await session.scalars(select(User).where(User.id.in_(trio)))).all()
    return sorted(u.last_name or u.first_name for u in users)
