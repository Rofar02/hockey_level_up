"""Team readiness for the captain (2026-10-09, release plan step 9): before
an ice or a game the captain sees who of the "going" players is fresh,
tired or overloaded -- by name (the app is for adults and the coach needs
the full picture, owner's call 2026-10-09), never the muscle map itself.

Built on steps 4-5: legs and back only (what skating loads), from the
player's own load history.

- overloaded: acute over the player's own habit (the same test that would
  change their week, app.core.week_load.is_overloaded), or a muscle near
  the map's cap right now;
- tired: a leg/back muscle at least half-loaded on the map right now;
- fresh: neither;
- no data: no gym or ice load at all in the last 28 days -- never shown
  as fresh.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.muscle_load import get_effective_muscle_load
from app.core.week_load import ACUTE_WINDOW_HOURS, HABITUAL_WINDOW_DAYS, is_overloaded
from app.models.exercise import MuscleGroup
from app.models.progress import UserMuscleLoad
from app.models.team import Team, TeamMembership
from app.models.team_event import TeamEvent, TeamEventAttendance, TeamEventAttendanceStatus
from app.models.user import User
from app.schemas.team_event import TeamReadinessPlayerRead, TeamReadinessRead
from app.services.joint_training_service import can_see_event
from app.services.week_load_service import _dose_events

READINESS_MUSCLES: tuple[MuscleGroup, ...] = (MuscleGroup.GLUTES, MuscleGroup.QUADS, MuscleGroup.BACK)
TIRED_LOAD = 5.0
OVERLOADED_LOAD = 8.5

STATUS_ORDER = {"overloaded": 0, "tired": 1, "fresh": 2, "no_data": 3}


async def player_readiness(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> str:
    events = await _dose_events(session, user_id, now - timedelta(days=HABITUAL_WINDOW_DAYS))
    loads = (
        await session.scalars(
            select(UserMuscleLoad).where(
                UserMuscleLoad.user_id == user_id, UserMuscleLoad.muscle_group.in_(READINESS_MUSCLES)
            )
        )
    ).all()
    current = {load.muscle_group: get_effective_muscle_load(load, now) for load in loads}
    if not events and not any(value > 0.1 for value in current.values()):
        return "no_data"
    acute_since = now - timedelta(hours=ACUTE_WINDOW_HOURS)
    windows = HABITUAL_WINDOW_DAYS * 24 / ACUTE_WINDOW_HOURS
    for muscle in READINESS_MUSCLES:
        acute = sum(dose for at, m, dose in events if m == muscle and at >= acute_since)
        habitual = sum(dose for _, m, dose in events if m == muscle) / windows
        if is_overloaded(acute, habitual) or current.get(muscle, 0.0) >= OVERLOADED_LOAD:
            return "overloaded"
    if any(value >= TIRED_LOAD for value in current.values()):
        return "tired"
    return "fresh"


class TeamReadinessService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def for_event(self, captain: User, team_id: uuid.UUID, event_id: uuid.UUID) -> TeamReadinessRead:
        team = await self._session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        if team.owner_id != captain.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the team captain can do this")
        event = await self._session.get(TeamEvent, event_id)
        if event is None or not await can_see_event(self._session, team.id, event):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        return await self.readiness_of_going(event, team.id)

    async def readiness_of_going(self, event: TeamEvent, team_id: uuid.UUID | None = None) -> TeamReadinessRead:
        """`team_id`: only that team's players -- on a joint training each
        captain sees their own (step 3.5)."""
        query = (
            select(User)
            .join(TeamEventAttendance, TeamEventAttendance.user_id == User.id)
            .where(
                TeamEventAttendance.team_event_id == event.id,
                TeamEventAttendance.status == TeamEventAttendanceStatus.GOING,
            )
        )
        if team_id is not None:
            query = query.join(TeamMembership, TeamMembership.user_id == User.id).where(TeamMembership.team_id == team_id)
        going = (await self._session.execute(query)).scalars().all()
        now = datetime.now(timezone.utc)
        players = [
            TeamReadinessPlayerRead(
                user_id=user.id,
                first_name=user.first_name,
                last_name=user.last_name,
                jersey_number=user.jersey_number,
                status=await player_readiness(self._session, user.id, now),
            )
            for user in going
        ]
        players.sort(key=lambda p: (STATUS_ORDER[p.status], p.last_name))
        counts = {key: sum(1 for p in players if p.status == key) for key in STATUS_ORDER}
        return TeamReadinessRead(
            going=len(players),
            fresh=counts["fresh"],
            tired=counts["tired"],
            overloaded=counts["overloaded"],
            no_data=counts["no_data"],
            players=players,
        )


def readiness_line(readiness: TeamReadinessRead) -> str:
    """One line for the captain's attendance summary push."""
    parts = [f"{readiness.fresh} свежие"]
    if readiness.tired:
        parts.append(f"{readiness.tired} устали")
    if readiness.overloaded:
        parts.append(f"{readiness.overloaded} перегружены")
    if readiness.no_data:
        parts.append(f"{readiness.no_data} без данных")
    return "Готовность: " + ", ".join(parts)
