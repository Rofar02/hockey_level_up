import uuid
from datetime import datetime, timedelta, timezone
from datetime import time as time_

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
    TeamEventDrillSection,
    TeamEventLineupGroup,
    TeamEventLineupSlot,
    TeamEventPublishStatus,
    TeamEventStatus,
    TeamEventType,
    TeamIceScheduleTemplate,
)
from app.models.user import User
from app.repositories.progress_repository import ProgressRepository
from app.repositories.team_event_repository import TeamEventRepository
from app.repositories.team_repository import TeamRepository
from app.schemas.team_event import (
    LINEUP_SLOTS,
    TeamCurrentLineupEventRead,
    TeamCurrentLineupRead,
    TeamEventAttendanceMemberRead,
    TeamEventAttendanceRead,
    TeamEventAttendanceRosterRead,
    DrillDiagram,
    TeamEventDrillRead,
    TeamEventDrillSectionRead,
    TeamEventLineupGroupRead,
    TeamEventLineupPlayerRead,
    TeamEventLineupRead,
    TeamEventNudgeResult,
    TeamEventRead,
    TeamIceScheduleTemplateRead,
)
from app.services.joint_training_service import can_see_event, event_team_ids, joint_event_ids_for_team
from app.services.push_service import send_push
from app.services.schedule_service import ScheduleService
from app.services.stat_service import get_effective_value

# -2h from starts_at -- see TeamEventAttendance's own docstring.
ATTENDANCE_DEADLINE = timedelta(hours=2)
# Nudge-button rate limit, checked server-side (see send_nudge).
NUDGE_MIN_INTERVAL = timedelta(hours=1)

# XP for a team training's day (see claim_team_training_reward) -- training
# only, a game is too unpredictable to credit a specific skill. Since
# 2026-10-08 it is the day's XP in place of the ordinary report XP, and the
# stats come from the report alone (one reward per day, not two).
TEAM_TRAINING_XP_BONUS = 50


class TeamEventService:
    """The TeamEvent shell, its board (TeamEventDrill), attendance
    (TeamEventAttendance), and lineup (TeamEventLineupGroup/Slot) -- one
    group shape for both a game's position-based lines and a training's
    mixed scrimmage teams, `color` valid only for the latter.

    Instant pushes (game scheduled, board/lineup published, reschedule,
    cancel) fire straight from the relevant method via _push_team --
    content-only edits (drill/group details, attendance) stay silent, per
    the v2 plan's notification table. The two TICK-based rows of that same
    table (attendance summary to the captain at the -2h deadline, "board
    not ready" the morning of a training) live in
    app/services/team_event_scheduler.py instead, same reasoning as
    reminder_scheduler.py vs. an instant push: both need a clock, not a
    triggering API call.

    Also the team-day reward: the first rewarded report for a day a
    TRAINING event took over earns the team-training XP instead of the
    ordinary report XP -- see claim_team_training_reward, called from
    TrainingDiaryService. Games grant nothing extra here.

    And CRUD for TeamIceScheduleTemplate (the recurring weekday+time slot
    a captain sets up) -- the actual stamping of future TeamEvent rows
    from active templates is a scheduler tick
    (team_event_scheduler._stamp_events_from_templates), not this service,
    same TICK-vs-instant-action split as the notification table above.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._teams = TeamRepository(session)
        self._events = TeamEventRepository(session)
        self._schedule = ScheduleService(session)

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
        if event_type == TeamEventType.GAME:
            # Training gets no "scheduled" push -- the team first hears
            # about it when the board is published (see publish_board).
            await self._push_team(
                team_id,
                "Назначена игра",
                f"Игра: {opponent_name} -- отметь явку",
            )
        sections = [] if event_type == TeamEventType.TRAINING else None
        return self._to_event_read(event, sections=sections, viewer_is_captain=True)

    async def reschedule_event(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, starts_at: datetime
    ) -> TeamEventRead:
        event = await self._require_captain_and_event(user, team_id, event_id)
        self._require_scheduled(event)
        event.starts_at = starts_at
        # "Going" players' days follow the event: old day back to what it
        # was, the new date's day taken over instead.
        for member in await self._going_members(event):
            await self._schedule.revert_team_event_days(member, event.id)
            await self._schedule.apply_team_event_to_day(member, event)
        await self._session.commit()
        await self._session.refresh(event)
        what = "тренировки" if event.event_type == TeamEventType.TRAINING else "игры"
        for event_team_id in await event_team_ids(self._session, event):
            await self._push_team(event_team_id, "Время перенесено", f"Изменилось время {what}")
        is_captain = True
        sections = await self._visible_sections(event, is_captain)
        return self._to_event_read(event, sections, viewer_is_captain=is_captain)

    async def cancel_event(self, user: User, team_id: uuid.UUID, event_id: uuid.UUID) -> TeamEventRead:
        event = await self._require_captain_and_event(user, team_id, event_id)
        self._require_scheduled(event)
        event.status = TeamEventStatus.CANCELLED
        for member in await self._going_members(event):
            await self._schedule.revert_team_event_days(member, event.id)
        await self._session.commit()
        await self._session.refresh(event)
        what = "Тренировка" if event.event_type == TeamEventType.TRAINING else "Игра"
        for event_team_id in await event_team_ids(self._session, event):
            await self._push_team(event_team_id, "Отмена", f"{what} отменена")
        is_captain = True
        sections = await self._visible_sections(event, is_captain)
        return self._to_event_read(event, sections, viewer_is_captain=is_captain)

    async def set_score(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, our: int | None, opponent: int | None
    ) -> TeamEventRead:
        """The captain enters the final score of a played game (2026-10-09)."""
        event = await self._require_captain_and_event(user, team_id, event_id)
        if event.event_type != TeamEventType.GAME:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Счёт бывает только у игры")
        self._require_scheduled(event)
        if (our is None) != (opponent is None):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Нужны оба числа счёта")
        if our is not None and event.starts_at > datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Игра ещё не началась")
        event.our_score = our
        event.opponent_score = opponent
        await self._session.commit()
        await self._session.refresh(event)
        sections = await self._visible_sections(event, True)
        return self._to_event_read(event, sections, viewer_is_captain=True)

    async def _going_members(self, event: TeamEvent) -> list[User]:
        rows = await self._events.list_attendance_for_event(event.id)
        going_ids = {row.user_id for row in rows if row.status == TeamEventAttendanceStatus.GOING}
        members = await self._event_members(event)
        return [member for member in members if member.id in going_ids]

    @staticmethod
    def _require_scheduled(event: TeamEvent) -> None:
        if event.status != TeamEventStatus.SCHEDULED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Event is already cancelled"
            )

    async def _push_team(self, team_id: uuid.UUID, title: str, body: str) -> None:
        members = await self._teams.list_members(team_id)
        for member in members:
            result = await self._session.execute(
                select(PushSubscription).where(PushSubscription.user_id == member.id)
            )
            for subscription in result.scalars().all():
                await send_push(self._session, subscription, title, body)
        # send_push flushes (not commits) a dead-subscription delete on a
        # 410 -- persist that here, same as the scheduler ticks below.
        await self._session.commit()

    async def list_events(self, user: User, team_id: uuid.UUID) -> list[TeamEventRead]:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        is_captain = team.owner_id == user.id
        events = list(await self._events.list_events_for_team(team_id))
        joint_ids = await joint_event_ids_for_team(self._session, team_id)
        if joint_ids:
            joint = [await self._events.get_event(event_id) for event_id in joint_ids]
            events += [e for e in joint if e is not None and e.status == TeamEventStatus.SCHEDULED]
            events.sort(key=lambda e: e.starts_at)
        reads = []
        for event in events:
            host_view = is_captain and event.team_id == team_id
            sections = await self._visible_sections(event, host_view)
            reads.append(await self._with_host(self._to_event_read(event, sections, viewer_is_captain=host_view), team_id))
        return reads

    async def _with_host(self, read: TeamEventRead, team_id: uuid.UUID) -> TeamEventRead:
        if read.team_id == team_id:
            return read
        host = await self._teams.get_by_id(read.team_id)
        return read.model_copy(update={"host_team_name": host.name if host is not None else None})

    async def get_event(self, user: User, team_id: uuid.UUID, event_id: uuid.UUID) -> TeamEventRead:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        event = await self._get_event_or_404(event_id, team_id, allow_guest=True)
        # A guest team's captain doesn't edit the host's board.
        is_captain = team.owner_id == user.id and event.team_id == team_id
        sections = await self._visible_sections(event, is_captain)
        return await self._with_host(self._to_event_read(event, sections, viewer_is_captain=is_captain), team_id)

    async def _visible_sections(
        self, event: TeamEvent, viewer_is_captain: bool
    ) -> list[tuple[TeamEventDrillSection, list[TeamEventDrill]]] | None:
        if event.event_type != TeamEventType.TRAINING:
            return None
        if not viewer_is_captain and event.board_status != TeamEventPublishStatus.PUBLISHED:
            return None
        sections = await self._events.list_sections_for_event(event.id)
        drills = await self._events.list_drills_for_event(event.id)
        by_section: dict[uuid.UUID, list[TeamEventDrill]] = {section.id: [] for section in sections}
        for drill in drills:
            by_section[drill.section_id].append(drill)
        return [(section, by_section[section.id]) for section in sections]

    # -- board: sections --

    async def add_section(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, name: str
    ) -> TeamEventDrillSectionRead:
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        order = len(await self._events.list_sections_for_event(event.id))
        section = await self._events.create_section(event.id, order, name.strip())
        await self._session.commit()
        return self._to_section_read(section, [])

    async def rename_section(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, section_id: uuid.UUID, name: str
    ) -> TeamEventDrillSectionRead:
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        section = await self._get_section_or_404(section_id, event.id)
        section.name = name.strip()
        await self._session.commit()
        await self._session.refresh(section)
        drills = await self._events.list_drills_for_section(section.id)
        return self._to_section_read(section, drills)

    async def delete_section(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, section_id: uuid.UUID
    ) -> None:
        """Deletes the section's drills too -- the frontend confirms first."""
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        section = await self._get_section_or_404(section_id, event.id)
        await self._events.delete_section(section)
        for index, remaining in enumerate(await self._events.list_sections_for_event(event.id)):
            remaining.order = index
        await self._session.commit()

    async def reorder_sections(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, section_ids: list[uuid.UUID]
    ) -> None:
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        existing = await self._events.list_sections_for_event(event.id)
        if {s.id for s in existing} != set(section_ids) or len(section_ids) != len(existing):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="section_ids must contain exactly this event's current sections",
            )
        by_id = {s.id: s for s in existing}
        for index, section_id in enumerate(section_ids):
            by_id[section_id].order = index
        await self._session.commit()

    # -- board: drills --

    async def add_drill(
        self,
        user: User,
        team_id: uuid.UUID,
        event_id: uuid.UUID,
        section_id: uuid.UUID,
        title: str,
        description: str | None,
        duration_minutes: int | None,
        diagram: DrillDiagram | None = None,
    ) -> TeamEventDrillRead:
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        section = await self._get_section_or_404(section_id, event.id)
        order = len(await self._events.list_drills_for_section(section.id))
        drill = await self._events.create_drill(
            event.id,
            section.id,
            order,
            title,
            description,
            duration_minutes,
            diagram.model_dump() if diagram is not None else None,
        )
        await self._session.commit()
        return self._to_drill_read(drill)

    async def update_drill(
        self,
        user: User,
        team_id: uuid.UUID,
        event_id: uuid.UUID,
        drill_id: uuid.UUID,
        section_id: uuid.UUID,
        title: str,
        description: str | None,
        duration_minutes: int | None,
    ) -> TeamEventDrillRead:
        """A different section_id moves the drill to the end of that
        section, closing the gap it left in the old one."""
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        drill = await self._get_drill_or_404(drill_id, event.id)
        if section_id != drill.section_id:
            target = await self._get_section_or_404(section_id, event.id)
            old_section_id = drill.section_id
            drill.order = len(await self._events.list_drills_for_section(target.id))
            drill.section_id = target.id
            await self._session.flush()
            await self._renumber_section_drills(old_section_id)
        drill.title = title
        drill.description = description
        drill.duration_minutes = duration_minutes
        await self._session.commit()
        await self._session.refresh(drill)
        return self._to_drill_read(drill)

    async def set_drill_diagram(
        self,
        user: User,
        team_id: uuid.UUID,
        event_id: uuid.UUID,
        drill_id: uuid.UUID,
        diagram: DrillDiagram | None,
    ) -> TeamEventDrillRead:
        """Replaces the drill's whole scheme (None clears it) -- the editor
        always sends the full diagram, never a patch. Silent like other
        content edits after publish (see update_drill)."""
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        drill = await self._get_drill_or_404(drill_id, event.id)
        drill.diagram = diagram.model_dump() if diagram is not None else None
        await self._session.commit()
        await self._session.refresh(drill)
        return self._to_drill_read(drill)

    async def delete_drill(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, drill_id: uuid.UUID
    ) -> None:
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        drill = await self._get_drill_or_404(drill_id, event.id)
        section_id = drill.section_id
        await self._events.delete_drill(drill)
        await self._renumber_section_drills(section_id)
        await self._session.commit()

    async def reorder_drills(
        self,
        user: User,
        team_id: uuid.UUID,
        event_id: uuid.UUID,
        section_id: uuid.UUID,
        drill_ids: list[uuid.UUID],
    ) -> list[TeamEventDrillRead]:
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        section = await self._get_section_or_404(section_id, event.id)
        existing = await self._events.list_drills_for_section(section.id)
        if {d.id for d in existing} != set(drill_ids) or len(drill_ids) != len(existing):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="drill_ids must contain exactly this section's current drills",
            )
        by_id = {d.id: d for d in existing}
        for index, drill_id in enumerate(drill_ids):
            by_id[drill_id].order = index
        await self._session.commit()
        reordered = await self._events.list_drills_for_section(section.id)
        return [self._to_drill_read(d) for d in reordered]

    async def _renumber_section_drills(self, section_id: uuid.UUID) -> None:
        for index, drill in enumerate(await self._events.list_drills_for_section(section_id)):
            drill.order = index

    async def publish_board(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> TeamEventRead:
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        # Idempotent -- re-publishing an already-published board is a no-op,
        # not an error (the captain may just hit the button again).
        already_published = event.board_status == TeamEventPublishStatus.PUBLISHED
        event.board_status = TeamEventPublishStatus.PUBLISHED
        await self._session.commit()
        await self._session.refresh(event)
        if not already_published:
            for event_team_id in await event_team_ids(self._session, event):
                await self._push_team(event_team_id, "План тренировки готов", "Доска тренировки опубликована")
        sections = await self._visible_sections(event, viewer_is_captain=True)
        return self._to_event_read(event, sections, viewer_is_captain=True)

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
        event = await self._get_event_or_404(event_id, team_id, allow_guest=True)
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
        # "Going" replaces the player's own day with the team event (see
        # ScheduleService.apply_team_event_to_day); "not going" puts it back.
        if attendance_status == TeamEventAttendanceStatus.GOING and event.status == TeamEventStatus.SCHEDULED:
            await self._schedule.apply_team_event_to_day(user, event)
        else:
            await self._schedule.revert_team_event_days(user, event.id)
        await self._session.commit()
        await self._session.refresh(attendance)
        return self._to_attendance_read(attendance)

    async def clear_my_attendance(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> None:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        event = await self._get_event_or_404(event_id, team_id, allow_guest=True)
        self._require_attendance_open(event)
        attendance = await self._events.get_attendance(event.id, user.id)
        if attendance is not None:
            await self._events.delete_attendance(attendance)
            await self._schedule.revert_team_event_days(user, event.id)
            await self._session.commit()

    async def get_attendance_roster(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> TeamEventAttendanceRosterRead:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        event = await self._get_event_or_404(event_id, team_id, allow_guest=True)
        # A joint training: one shared list of marks for both teams -- but
        # why a player of the other team isn't coming stays in their team.
        members = await self._event_members(event)
        own_ids = {member.id for member in await self._teams.list_members(team_id)}
        rows = await self._events.list_attendance_for_event(event.id)
        by_user_id = {row.user_id: row for row in rows}

        going, not_going, unmarked = [], [], []
        for member in members:
            row = by_user_id.get(member.id)
            entry = self._to_attendance_member_read(member, row)
            if member.id not in own_ids:
                entry = entry.model_copy(update={"reason": None, "reason_note": None})
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
        # Marks are closed -- nobody can answer the reminder any more.
        self._require_attendance_open(event)
        if event.last_nudge_sent_at is not None and now - event.last_nudge_sent_at < NUDGE_MIN_INTERVAL:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Nudge already sent within the last hour",
            )

        # A joint training: the guest teams' players are reminded too.
        members = await self._event_members(event)
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
        return self._group_read(group, [])

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
        return await self._lineup_group_read(group)

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
        slot: str | None = None,
    ) -> TeamEventLineupGroupRead:
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        event = await self._get_event_or_404(event_id, team_id)
        if target_user_id not in {member.id for member in await self._event_members(event)}:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not a member of this team"
            )
        group = await self._get_lineup_group_or_404(group_id, event.id)
        # Upsert -- a player already placed elsewhere in this event just
        # moves (the unique constraint on (team_event_id, user_id) is what
        # enforces "at most one group at a time", not this check).
        if slot is not None and slot not in LINEUP_SLOTS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown slot")
        placed = await self._events.upsert_lineup_slot(event.id, group.id, target_user_id)
        if slot is not None and slot != "G":
            # One player per spot in a line: whoever held it stays in the
            # group without a spot (goalies can share G).
            holders = await self._session.scalars(
                select(TeamEventLineupSlot).where(
                    TeamEventLineupSlot.group_id == group.id,
                    TeamEventLineupSlot.slot_position == slot,
                    TeamEventLineupSlot.user_id != target_user_id,
                )
            )
            for holder in holders.all():
                holder.slot_position = None
        placed.slot_position = slot
        await self._session.commit()
        return await self._lineup_group_read(group)

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
        event = await self._get_event_or_404(event_id, team_id, allow_guest=True)
        is_captain = team.owner_id == user.id and event.team_id == team_id
        if not is_captain and event.lineup_status != TeamEventPublishStatus.PUBLISHED:
            return TeamEventLineupRead(lineup_status=event.lineup_status)
        return await self._build_lineup_read(event)

    async def get_current_lineup(self, user: User, team_id: uuid.UUID) -> TeamCurrentLineupRead:
        """"Состав по звеньям" (2026-10-09): the next game's lineup, or the
        last game's when nothing is scheduled ahead."""
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        now = datetime.now(timezone.utc)
        base = select(TeamEvent).where(
            TeamEvent.team_id == team.id,
            TeamEvent.event_type == TeamEventType.GAME,
            TeamEvent.status == TeamEventStatus.SCHEDULED,
        )
        # A game stays "next" until 3 hours after its start.
        event = (
            await self._session.scalars(
                base.where(TeamEvent.starts_at >= now - timedelta(hours=3)).order_by(TeamEvent.starts_at).limit(1)
            )
        ).first()
        if event is None:
            event = (
                await self._session.scalars(base.order_by(TeamEvent.starts_at.desc()).limit(1))
            ).first()
        if event is None:
            return TeamCurrentLineupRead()
        is_captain = team.owner_id == user.id
        if not is_captain and event.lineup_status != TeamEventPublishStatus.PUBLISHED:
            lineup = TeamEventLineupRead(lineup_status=event.lineup_status)
        else:
            lineup = await self._build_lineup_read(event)
        return TeamCurrentLineupRead(
            event=TeamCurrentLineupEventRead(id=event.id, starts_at=event.starts_at, opponent_name=event.opponent_name),
            lineup=lineup,
        )

    async def publish_lineup(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> TeamEventLineupRead:
        event = await self._require_captain_and_event(user, team_id, event_id)
        # Idempotent, same reasoning as publish_board.
        already_published = event.lineup_status == TeamEventPublishStatus.PUBLISHED
        event.lineup_status = TeamEventPublishStatus.PUBLISHED
        await self._session.commit()
        await self._session.refresh(event)
        if not already_published:
            for event_team_id in await event_team_ids(self._session, event):
                await self._push_team(event_team_id, "Состав опубликован", "Тренер опубликовал состав")
        return await self._build_lineup_read(event)

    async def _build_lineup_read(self, event: TeamEvent) -> TeamEventLineupRead:
        # A joint training's lines can mix players of both teams.
        members = await self._event_members(event)
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

        slot_by_user = {slot.user_id: slot.slot_position for slot in slots}
        reads = await self._player_reads(members, slot_by_user)
        group_reads = [
            self._group_read(group, [reads[p.id] for p in players_by_group[group.id]]) for group in groups
        ]
        unassigned = [reads[m.id] for m in members if m.id not in assigned_user_ids]
        return TeamEventLineupRead(
            lineup_status=event.lineup_status, groups=group_reads, unassigned=unassigned
        )

    async def _lineup_group_read(self, group: TeamEventLineupGroup) -> TeamEventLineupGroupRead:
        slots = (
            await self._session.scalars(
                select(TeamEventLineupSlot).where(TeamEventLineupSlot.group_id == group.id)
            )
        ).all()
        # Only players still in the event -- someone who left the team (or
        # whose team left a joint training) isn't shown in a line.
        event = await self._events.get_event(group.team_event_id)
        participant_ids = {member.id for member in await self._event_members(event)}
        slot_by_user = {slot.user_id: slot.slot_position for slot in slots if slot.user_id in participant_ids}
        if not slot_by_user:
            return self._group_read(group, [])
        users = list((await self._session.scalars(select(User).where(User.id.in_(slot_by_user)))).all())
        reads = await self._player_reads(users, slot_by_user)
        return self._group_read(group, [reads[u.id] for u in users])

    async def _player_reads(
        self, users: list[User], slot_by_user: dict[uuid.UUID, str | None]
    ) -> dict[uuid.UUID, TeamEventLineupPlayerRead]:
        """Mini-card data for each player: spot, jersey, level, the card
        "ОБЩИЙ" and the six stats behind it -- one stats query for all."""
        stats = await ProgressRepository(self._session).list_stats_for_users([u.id for u in users])
        now = datetime.now(timezone.utc)
        by_user: dict[uuid.UUID, dict[str, float]] = {}
        for stat in stats:
            by_user.setdefault(stat.user_id, {})[str(stat.stat_type)] = round(get_effective_value(stat, now), 1)
        reads = {}
        for member in users:
            values = by_user.get(member.id, {})
            reads[member.id] = TeamEventLineupPlayerRead(
                user_id=member.id,
                first_name=member.first_name,
                last_name=member.last_name,
                avatar_url=member.avatar_url,
                position=member.position,
                slot=slot_by_user.get(member.id),
                jersey_number=member.jersey_number,
                level=member.level,
                rating=round(sum(values.values()) / len(values)) if values else None,
                stats=values,
            )
        return reads

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
    def _group_read(
        group: TeamEventLineupGroup, players: list[TeamEventLineupPlayerRead]
    ) -> TeamEventLineupGroupRead:
        order = {slot: index for index, slot in enumerate(LINEUP_SLOTS)}
        players = sorted(players, key=lambda p: (order.get(p.slot or "", 99), p.last_name))
        slots = {p.slot for p in players if p.slot is not None}
        if slots and slots <= {"LW", "C", "RW"}:
            kind = "forwards"
        elif slots and slots <= {"LD", "RD"}:
            kind = "defense"
        elif slots == {"G"}:
            kind = "goalies"
        else:
            kind = "mixed"
        ratings = [p.rating for p in players if p.rating is not None]
        return TeamEventLineupGroupRead(
            id=group.id,
            name=group.name,
            color=group.color,
            players=players,
            kind=kind,
            rating=round(sum(ratings) / len(ratings)) if ratings else None,
        )

    # -- rewards --

    async def claim_team_training_reward(
        self, user: User, team_event_id: uuid.UUID, note: str | None
    ) -> bool:
        """Called by TrainingDiaryService when it rewards the report for a
        day a team training took over (DayPlan.team_event_id): whether this
        day earns TEAM_TRAINING_XP_BONUS, once per player per event. The
        TeamEventDiaryEntry row is the "already claimed" marker (players
        rewarded through the old team diary tab aren't rewarded twice). A
        game, a vanished event or a player no longer in the team gets
        nothing. Credits nothing itself -- the caller does. Doesn't commit.
        """
        event = await self._events.get_event(team_event_id)
        if event is None or event.event_type != TeamEventType.TRAINING:
            return False
        # A joint training rewards the accepted guest teams' players too.
        if not any(
            [await self._teams.get_membership(event_team_id, user.id) is not None for event_team_id in await event_team_ids(self._session, event)]
        ):
            return False
        if await self._events.get_diary_entry(event.id, user.id) is not None:
            return False
        await self._events.create_diary_entry(event.id, user.id, note)
        return True

    # -- ice schedule template --

    async def create_template(
        self, user: User, team_id: uuid.UUID, weekday: int, start_time: time_
    ) -> TeamIceScheduleTemplateRead:
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        template = await self._events.create_template(team_id, weekday, start_time)
        await self._session.commit()
        return self._to_template_read(template)

    async def list_templates(
        self, user: User, team_id: uuid.UUID
    ) -> list[TeamIceScheduleTemplateRead]:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        templates = await self._events.list_templates_for_team(team_id)
        return [self._to_template_read(t) for t in templates]

    async def set_template_active(
        self, user: User, team_id: uuid.UUID, template_id: uuid.UUID, active: bool
    ) -> TeamIceScheduleTemplateRead:
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        template = await self._get_template_or_404(template_id, team_id)
        # Deactivating never touches already-stamped TeamEvent rows -- see
        # the model's own docstring. Reactivating just lets the scheduler
        # pick the slot back up on its next tick.
        template.active = active
        await self._session.commit()
        await self._session.refresh(template)
        return self._to_template_read(template)

    async def delete_template(
        self, user: User, team_id: uuid.UUID, template_id: uuid.UUID
    ) -> None:
        team = await self._get_team_or_404(team_id)
        self._require_captain(user, team)
        template = await self._get_template_or_404(template_id, team_id)
        # source_template_id is ON DELETE SET NULL (see TeamEvent) -- any
        # TeamEvent this already stamped just loses the back-reference, it
        # isn't cascaded away.
        await self._events.delete_template(template)
        await self._session.commit()

    async def _get_template_or_404(
        self, template_id: uuid.UUID, team_id: uuid.UUID
    ) -> TeamIceScheduleTemplate:
        template = await self._events.get_template(template_id)
        if template is None or template.team_id != team_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        return template

    @staticmethod
    def _to_template_read(template: TeamIceScheduleTemplate) -> TeamIceScheduleTemplateRead:
        return TeamIceScheduleTemplateRead(
            id=template.id,
            weekday=template.weekday,
            start_time=template.start_time,
            active=template.active,
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

    async def _get_event_or_404(
        self, event_id: uuid.UUID, team_id: uuid.UUID, allow_guest: bool = False
    ) -> TeamEvent:
        """The event as seen from the team in the URL. Writes stay with the
        host team; `allow_guest` lets an accepted guest team of a joint
        training read and mark attendance (release plan step 3.5) -- the
        single place that decides who sees a joint event."""
        event = await self._events.get_event(event_id)
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        if event.team_id != team_id and not (allow_guest and await can_see_event(self._session, team_id, event)):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        return event

    async def _event_members(self, event: TeamEvent) -> list[User]:
        """Players of the host and of every accepted guest team."""
        members: list[User] = []
        for event_team_id in await event_team_ids(self._session, event):
            members.extend(await self._teams.list_members(event_team_id))
        return members

    async def _get_section_or_404(
        self, section_id: uuid.UUID, team_event_id: uuid.UUID
    ) -> TeamEventDrillSection:
        section = await self._events.get_section(section_id)
        if section is None or section.team_event_id != team_event_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
        return section

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
            id=drill.id,
            section_id=drill.section_id,
            order=drill.order,
            title=drill.title,
            description=drill.description,
            duration_minutes=drill.duration_minutes,
            diagram=DrillDiagram.model_validate(drill.diagram) if drill.diagram is not None else None,
        )

    @classmethod
    def _to_section_read(
        cls, section: TeamEventDrillSection, drills: list[TeamEventDrill]
    ) -> TeamEventDrillSectionRead:
        return TeamEventDrillSectionRead(
            id=section.id,
            order=section.order,
            name=section.name,
            drills=[cls._to_drill_read(d) for d in drills],
        )

    @classmethod
    def _to_event_read(
        cls,
        event: TeamEvent,
        sections: list[tuple[TeamEventDrillSection, list[TeamEventDrill]]] | None,
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
            sections=None
            if sections is None
            else [cls._to_section_read(section, drills) for section, drills in sections],
            created_at=event.created_at,
            our_score=event.our_score,
            opponent_score=event.opponent_score,
        )
