import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team
from app.models.team_event import (
    TeamEvent,
    TeamEventDrill,
    TeamEventPublishStatus,
    TeamEventType,
)
from app.models.user import User
from app.repositories.team_event_repository import TeamEventRepository
from app.repositories.team_repository import TeamRepository
from app.schemas.team_event import TeamEventDrillRead, TeamEventRead


class TeamEventService:
    """Board (TeamEventDrill) + the TeamEvent shell it lives on. Attendance,
    lineup and notification wiring are separate, later slices of the v2
    plan -- not built here (see TeamEvent's own board_not_ready_sent_at/
    attendance_summary_sent_at/last_nudge_sent_at fields, unused so far).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._teams = TeamRepository(session)
        self._events = TeamEventRepository(session)

    # -- TeamEvent --

    async def create_event(
        self,
        user: User,
        team_id: uuid.UUID,
        event_type: TeamEventType,
        starts_at: datetime,
        opponent_name: str | None,
    ) -> TeamEventRead:
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        if event_type == TeamEventType.GAME and not (opponent_name and opponent_name.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="opponent_name is required for a game",
            )
        if event_type == TeamEventType.TRAINING and opponent_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="opponent_name only applies to a game",
            )
        event = await self._events.create_event(team_id, event_type, starts_at, opponent_name)
        await self._session.commit()
        drills = [] if event_type == TeamEventType.TRAINING else None
        return self._to_event_read(event, drills=drills, viewer_is_captain=True)

    async def list_events(self, user: User, team_id: uuid.UUID) -> list[TeamEventRead]:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        is_captain = team.owner_id == user.id
        events = await self._events.list_events_for_team(team_id)
        reads = []
        for event in events:
            drills = await self._visible_drills(event, is_captain)
            reads.append(self._to_event_read(event, drills, viewer_is_captain=is_captain))
        return reads

    async def get_event(self, user: User, team_id: uuid.UUID, event_id: uuid.UUID) -> TeamEventRead:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        event = await self._get_event_or_404(event_id, team_id)
        is_captain = team.owner_id == user.id
        drills = await self._visible_drills(event, is_captain)
        return self._to_event_read(event, drills, viewer_is_captain=is_captain)

    async def _visible_drills(
        self, event: TeamEvent, viewer_is_captain: bool
    ) -> list[TeamEventDrill] | None:
        if event.event_type != TeamEventType.TRAINING:
            return None
        if not viewer_is_captain and event.board_status != TeamEventPublishStatus.PUBLISHED:
            return None
        return await self._events.list_drills_for_event(event.id)

    # -- board --

    async def add_drill(
        self,
        user: User,
        team_id: uuid.UUID,
        event_id: uuid.UUID,
        title: str,
        description: str | None,
    ) -> TeamEventDrillRead:
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        order = await self._events.next_drill_order(event.id)
        drill = await self._events.create_drill(event.id, order, title, description)
        await self._session.commit()
        return self._to_drill_read(drill)

    async def update_drill(
        self,
        user: User,
        team_id: uuid.UUID,
        event_id: uuid.UUID,
        drill_id: uuid.UUID,
        title: str,
        description: str | None,
    ) -> TeamEventDrillRead:
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        drill = await self._get_drill_or_404(drill_id, event.id)
        drill.title = title
        drill.description = description
        await self._session.commit()
        await self._session.refresh(drill)
        return self._to_drill_read(drill)

    async def delete_drill(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, drill_id: uuid.UUID
    ) -> None:
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        drill = await self._get_drill_or_404(drill_id, event.id)
        await self._events.delete_drill(drill)
        remaining = await self._events.list_drills_for_event(event.id)
        for index, remaining_drill in enumerate(remaining):
            remaining_drill.order = index
        await self._session.commit()

    async def reorder_drills(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, drill_ids: list[uuid.UUID]
    ) -> list[TeamEventDrillRead]:
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        existing = await self._events.list_drills_for_event(event.id)
        if {d.id for d in existing} != set(drill_ids) or len(drill_ids) != len(existing):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="drill_ids must contain exactly this event's current drills",
            )
        by_id = {d.id: d for d in existing}
        for index, drill_id in enumerate(drill_ids):
            by_id[drill_id].order = index
        await self._session.commit()
        reordered = await self._events.list_drills_for_event(event.id)
        return [self._to_drill_read(d) for d in reordered]

    async def publish_board(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> TeamEventRead:
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        # Idempotent -- re-publishing an already-published board is a no-op,
        # not an error (the captain may just hit the button again).
        event.board_status = TeamEventPublishStatus.PUBLISHED
        await self._session.commit()
        await self._session.refresh(event)
        drills = await self._events.list_drills_for_event(event.id)
        return self._to_event_read(event, drills, viewer_is_captain=True)

    # -- shared guards --

    async def _require_captain_and_training_event(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> TeamEvent:
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        event = await self._get_event_or_404(event_id, team_id)
        if event.event_type != TeamEventType.TRAINING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="A game has no board"
            )
        return event

    async def _get_team_or_404(self, team_id: uuid.UUID) -> Team:
        team = await self._teams.get_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        return team

    async def _get_event_or_404(self, event_id: uuid.UUID, team_id: uuid.UUID) -> TeamEvent:
        event = await self._events.get_event(event_id)
        if event is None or event.team_id != team_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        return event

    async def _get_drill_or_404(
        self, drill_id: uuid.UUID, team_event_id: uuid.UUID
    ) -> TeamEventDrill:
        drill = await self._events.get_drill(drill_id)
        if drill is None or drill.team_event_id != team_event_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Drill not found")
        return drill

    async def _require_member(self, user: User, team: Team) -> None:
        if await self._teams.get_membership(team.id, user.id) is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this team"
            )

    @staticmethod
    def _require_captain(user: User, team: Team) -> None:
        if team.owner_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Only the team captain can do this"
            )

    @staticmethod
    def _to_drill_read(drill: TeamEventDrill) -> TeamEventDrillRead:
        return TeamEventDrillRead(
            id=drill.id, order=drill.order, title=drill.title, description=drill.description
        )

    @classmethod
    def _to_event_read(
        cls,
        event: TeamEvent,
        drills: list[TeamEventDrill] | None,
        viewer_is_captain: bool,
    ) -> TeamEventRead:
        return TeamEventRead(
            id=event.id,
            team_id=event.team_id,
            event_type=event.event_type,
            status=event.status,
            starts_at=event.starts_at,
            opponent_name=event.opponent_name,
            board_status=event.board_status,
            drills=None if drills is None else [cls._to_drill_read(d) for d in drills],
            created_at=event.created_at,
        )
