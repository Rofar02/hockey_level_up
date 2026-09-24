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
    TeamEventLineupGroup,
    TeamEventLineupSlot,
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
    TeamEventLineupGroupRead,
    TeamEventLineupPlayerRead,
    TeamEventLineupRead,
    TeamEventNudgeResult,
    TeamEventRead,
)
from app.services.push_service import send_push

# -2h from starts_at -- see TeamEventAttendance's own docstring.
ATTENDANCE_DEADLINE = timedelta(hours=2)
# Nudge-button rate limit, checked server-side (see send_nudge).
NUDGE_MIN_INTERVAL = timedelta(hours=1)


class TeamEventService:
    """The TeamEvent shell, its board (TeamEventDrill), attendance
    (TeamEventAttendance), and lineup (TeamEventLineupGroup/Slot) -- one
    group shape for both a game's position-based lines and a training's
    mixed scrimmage teams, `color` valid only for the latter. The rest of
    the notification table (publish/starts_at-change/cancel pushes, the
    attendance-summary and "board not ready" scheduler ticks) is a
    separate, later slice of the v2 plan -- not built here (see TeamEvent's
    own attendance_summary_sent_at/board_not_ready_sent_at fields, unused
    so far).
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

    # -- lineup --

    async def create_lineup_group(
        self,
        user: User,
        team_id: uuid.UUID,
        event_id: uuid.UUID,
        name: str | None,
        color: str | None,
    ) -> TeamEventLineupGroupRead:
        event = await self._require_captain_and_event(user, team_id, event_id)
        self._require_color_only_for_training(event, color)
        order = await self._events.next_lineup_group_order(event.id)
        group = await self._events.create_lineup_group(event.id, order, name, color)
        await self._session.commit()
        return self._to_lineup_group_read(group, players=[])

    async def update_lineup_group(
        self,
        user: User,
        team_id: uuid.UUID,
        event_id: uuid.UUID,
        group_id: uuid.UUID,
        name: str | None,
        color: str | None,
    ) -> TeamEventLineupGroupRead:
        event = await self._require_captain_and_event(user, team_id, event_id)
        self._require_color_only_for_training(event, color)
        group = await self._get_lineup_group_or_404(group_id, event.id)
        group.name = name
        group.color = color
        await self._session.commit()
        await self._session.refresh(group)
        players = await self._lineup_group_players(group.id)
        return self._to_lineup_group_read(group, players)

    async def delete_lineup_group(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, group_id: uuid.UUID
    ) -> None:
        event = await self._require_captain_and_event(user, team_id, event_id)
        group = await self._get_lineup_group_or_404(group_id, event.id)
        # Slots cascade with the group (ondelete="CASCADE") -- their players
        # simply become unassigned again, no separate cleanup needed.
        await self._events.delete_lineup_group(group)
        remaining = await self._events.list_lineup_groups_for_event(event.id)
        for index, remaining_group in enumerate(remaining):
            remaining_group.order = index
        await self._session.commit()

    async def assign_player(
        self,
        user: User,
        team_id: uuid.UUID,
        event_id: uuid.UUID,
        target_user_id: uuid.UUID,
        group_id: uuid.UUID,
    ) -> TeamEventLineupGroupRead:
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        event = await self._get_event_or_404(event_id, team_id)
        if await self._teams.get_membership(team_id, target_user_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not a member of this team"
            )
        group = await self._get_lineup_group_or_404(group_id, event.id)
        # Upsert -- a player already placed elsewhere in this event just
        # moves (the unique constraint on (team_event_id, user_id) is what
        # enforces "at most one group at a time", not this check).
        await self._events.upsert_lineup_slot(event.id, group.id, target_user_id)
        await self._session.commit()
        players = await self._lineup_group_players(group.id)
        return self._to_lineup_group_read(group, players)

    async def unassign_player(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, target_user_id: uuid.UUID
    ) -> None:
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        event = await self._get_event_or_404(event_id, team_id)
        slot = await self._events.get_lineup_slot(event.id, target_user_id)
        if slot is not None:
            await self._events.delete_lineup_slot(slot)
            await self._session.commit()

    async def get_lineup(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> TeamEventLineupRead:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        event = await self._get_event_or_404(event_id, team_id)
        is_captain = team.owner_id == user.id
        if not is_captain and event.lineup_status != TeamEventPublishStatus.PUBLISHED:
            return TeamEventLineupRead(lineup_status=event.lineup_status)
        return await self._build_lineup_read(event)

    async def publish_lineup(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> TeamEventLineupRead:
        event = await self._require_captain_and_event(user, team_id, event_id)
        # Idempotent, same reasoning as publish_board.
        event.lineup_status = TeamEventPublishStatus.PUBLISHED
        await self._session.commit()
        await self._session.refresh(event)
        return await self._build_lineup_read(event)

    async def _build_lineup_read(self, event: TeamEvent) -> TeamEventLineupRead:
        members = await self._teams.list_members(event.team_id)
        groups = await self._events.list_lineup_groups_for_event(event.id)
        slots = await self._events.list_lineup_slots_for_event(event.id)
        members_by_id = {m.id: m for m in members}

        players_by_group: dict[uuid.UUID, list[User]] = {g.id: [] for g in groups}
        assigned_user_ids: set[uuid.UUID] = set()
        for slot in slots:
            member = members_by_id.get(slot.user_id)
            if member is not None and slot.group_id in players_by_group:
                players_by_group[slot.group_id].append(member)
                assigned_user_ids.add(slot.user_id)

        group_reads = [
            self._to_lineup_group_read(group, players_by_group[group.id]) for group in groups
        ]
        unassigned = [
            self._to_lineup_player_read(m) for m in members if m.id not in assigned_user_ids
        ]
        return TeamEventLineupRead(
            lineup_status=event.lineup_status, groups=group_reads, unassigned=unassigned
        )

    async def _lineup_group_players(self, group_id: uuid.UUID) -> list[User]:
        slots = await self._session.execute(
            select(TeamEventLineupSlot).where(TeamEventLineupSlot.group_id == group_id)
        )
        user_ids = [slot.user_id for slot in slots.scalars().all()]
        if not user_ids:
            return []
        result = await self._session.execute(select(User).where(User.id.in_(user_ids)))
        return list(result.scalars().all())

    @staticmethod
    def _require_color_only_for_training(event: TeamEvent, color: str | None) -> None:
        if color and event.event_type != TeamEventType.TRAINING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="color only applies to a training scrimmage group",
            )

    async def _get_lineup_group_or_404(
        self, group_id: uuid.UUID, team_event_id: uuid.UUID
    ) -> TeamEventLineupGroup:
        group = await self._events.get_lineup_group(group_id)
        if group is None or group.team_event_id != team_event_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        return group

    @staticmethod
    def _to_lineup_player_read(member: User) -> TeamEventLineupPlayerRead:
        return TeamEventLineupPlayerRead(
            user_id=member.id,
            first_name=member.first_name,
            last_name=member.last_name,
            avatar_url=member.avatar_url,
            position=member.position,
        )

    @classmethod
    def _to_lineup_group_read(
        cls, group: TeamEventLineupGroup, players: list[User]
    ) -> TeamEventLineupGroupRead:
        return TeamEventLineupGroupRead(
            id=group.id,
            name=group.name,
            color=group.color,
            players=[cls._to_lineup_player_read(p) for p in players],
        )

    # -- shared guards --

    async def _require_captain_and_event(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> TeamEvent:
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        return await self._get_event_or_404(event_id, team_id)

    async def _require_captain_and_training_event(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> TeamEvent:
        event = await self._require_captain_and_event(user, team_id, event_id)
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
