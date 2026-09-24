import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.push_subscription import PushSubscription
from app.models.team import Team
from app.models.team_event import (
    TeamEvent,
    TeamEventAbsenceReason,
    TeamEventAttendance,
    TeamEventAttendanceStatus,
    TeamEventDrill,
    TeamEventPublishStatus,
    TeamEventType,
)
from app.models.user import User
from app.repositories.team_event_repository import TeamEventRepository
from app.repositories.team_repository import TeamRepository
from app.schemas.team_event import (
    TeamEventAttendanceMemberRead,
    TeamEventAttendanceRead,
    TeamEventAttendanceRosterRead,
    TeamEventDrillRead,
    TeamEventNudgeResult,
    TeamEventRead,
)
from app.services.push_service import send_push

# -2h from starts_at -- see TeamEventAttendance's own docstring.
ATTENDANCE_DEADLINE = timedelta(hours=2)
# Nudge-button rate limit, checked server-side (see send_nudge).
NUDGE_MIN_INTERVAL = timedelta(hours=1)


class TeamEventService:
    """The TeamEvent shell, its board (TeamEventDrill), and attendance
    (TeamEventAttendance) -- going/not_going/unmarked, the -2h freeze, and
    the captain's rate-limited nudge push. Lineup and the rest of the
    notification table (publish/starts_at-change/cancel pushes, the
    attendance-summary and "board not ready" scheduler ticks) are separate,
    later slices of the v2 plan -- not built here (see TeamEvent's own
    attendance_summary_sent_at/board_not_ready_sent_at fields, unused so
    far).
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

    # -- attendance --

    async def set_my_attendance(
        self,
        user: User,
        team_id: uuid.UUID,
        event_id: uuid.UUID,
        attendance_status: TeamEventAttendanceStatus,
        reason: TeamEventAbsenceReason | None,
        reason_note: str | None,
    ) -> TeamEventAttendanceRead:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        event = await self._get_event_or_404(event_id, team_id)
        self._require_attendance_open(event)
        if attendance_status == TeamEventAttendanceStatus.NOT_GOING and reason is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="reason is required when marking not_going",
            )
        if attendance_status == TeamEventAttendanceStatus.GOING and (reason or reason_note):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="reason/reason_note only apply to not_going",
            )
        attendance = await self._events.upsert_attendance(
            event.id, user.id, attendance_status, reason, reason_note
        )
        await self._session.commit()
        await self._session.refresh(attendance)
        return self._to_attendance_read(attendance)

    async def clear_my_attendance(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> None:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        event = await self._get_event_or_404(event_id, team_id)
        self._require_attendance_open(event)
        attendance = await self._events.get_attendance(event.id, user.id)
        if attendance is not None:
            await self._events.delete_attendance(attendance)
            await self._session.commit()

    async def get_attendance_roster(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> TeamEventAttendanceRosterRead:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        event = await self._get_event_or_404(event_id, team_id)
        members = await self._teams.list_members(team_id)
        rows = await self._events.list_attendance_for_event(event.id)
        by_user_id = {row.user_id: row for row in rows}

        going, not_going, unmarked = [], [], []
        for member in members:
            row = by_user_id.get(member.id)
            entry = self._to_attendance_member_read(member, row)
            if row is None:
                unmarked.append(entry)
            elif row.status == TeamEventAttendanceStatus.GOING:
                going.append(entry)
            else:
                not_going.append(entry)

        return TeamEventAttendanceRosterRead(
            is_locked=self._is_attendance_locked(event),
            going=going,
            not_going=not_going,
            unmarked=unmarked,
        )

    async def send_nudge(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> TeamEventNudgeResult:
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        event = await self._get_event_or_404(event_id, team_id)
        now = datetime.now(timezone.utc)
        if event.last_nudge_sent_at is not None and now - event.last_nudge_sent_at < NUDGE_MIN_INTERVAL:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Nudge already sent within the last hour",
            )

        members = await self._teams.list_members(team_id)
        rows = await self._events.list_attendance_for_event(event.id)
        responded_user_ids = {row.user_id for row in rows}
        unmarked_members = [m for m in members if m.id not in responded_user_ids]

        title = "Не забудь отметить явку"
        body = self._nudge_body(event)
        notified_count = 0
        for member in unmarked_members:
            result = await self._session.execute(
                select(PushSubscription).where(PushSubscription.user_id == member.id)
            )
            for subscription in result.scalars().all():
                if await send_push(self._session, subscription, title, body):
                    notified_count += 1

        event.last_nudge_sent_at = now
        await self._session.commit()
        return TeamEventNudgeResult(notified_count=notified_count, last_nudge_sent_at=now)

    @staticmethod
    def _nudge_body(event: TeamEvent) -> str:
        what = "тренировка" if event.event_type == TeamEventType.TRAINING else "игра"
        return f"Отметь, придёшь ли на {what}"

    def _is_attendance_locked(self, event: TeamEvent, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return now >= event.starts_at - ATTENDANCE_DEADLINE

    def _require_attendance_open(self, event: TeamEvent) -> None:
        if self._is_attendance_locked(event):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Attendance is locked -- the 2h deadline has passed",
            )

    @staticmethod
    def _to_attendance_read(attendance: TeamEventAttendance) -> TeamEventAttendanceRead:
        return TeamEventAttendanceRead(
            status=attendance.status,
            reason=attendance.reason,
            reason_note=attendance.reason_note,
            responded_at=attendance.responded_at,
        )

    @staticmethod
    def _to_attendance_member_read(
        member: User, attendance: TeamEventAttendance | None
    ) -> TeamEventAttendanceMemberRead:
        return TeamEventAttendanceMemberRead(
            user_id=member.id,
            first_name=member.first_name,
            last_name=member.last_name,
            avatar_url=member.avatar_url,
            reason=attendance.reason if attendance else None,
            reason_note=attendance.reason_note if attendance else None,
            responded_at=attendance.responded_at if attendance else None,
        )

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
