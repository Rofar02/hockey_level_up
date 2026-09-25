import uuid
from datetime import datetime, timedelta, timezone
from datetime import time as time_

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.handlers.block_completed import (
    DIMINISHING_EXPONENT,
    LEVEL_UP_EVENT,
    STAT_HARD_CAP,
    xp_to_next_level,
)
from app.models.exercise import TargetStat
from app.models.progress import StatHistory, UserStat
from app.models.push_subscription import PushSubscription
from app.models.team import Team
from app.models.team_event import (
    TeamEvent,
    TeamEventAbsenceReason,
    TeamEventAttendance,
    TeamEventAttendanceStatus,
    TeamEventDiaryEntry,
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
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.team_event_repository import TeamEventRepository
from app.repositories.team_repository import TeamRepository
from app.schemas.team_event import (
    TeamEventAttendanceMemberRead,
    TeamEventAttendanceRead,
    TeamEventAttendanceRosterRead,
    TeamEventDiaryEntryRead,
    TeamEventDrillRead,
    TeamEventDrillSectionRead,
    TeamEventLineupGroupRead,
    TeamEventLineupPlayerRead,
    TeamEventLineupRead,
    TeamEventNudgeResult,
    TeamEventRead,
    TeamIceScheduleTemplateRead,
)
from app.services.push_service import send_push
from app.services.schedule_service import ScheduleService

# -2h from starts_at -- see TeamEventAttendance's own docstring.
ATTENDANCE_DEADLINE = timedelta(hours=2)
# Nudge-button rate limit, checked server-side (see send_nudge).
NUDGE_MIN_INTERVAL = timedelta(hours=1)

# Rewards for a TRAINING diary entry (see save_diary_entry) -- training
# only, per the v2 plan (a game is too unpredictable to credit a specific
# skill). Same diminishing-returns curve as block_completed.stat_consumer
# (STAT_HARD_CAP/DIMINISHING_EXPONENT imported from there, not
# redeclared, so the two curves can't drift apart), just with no
# Exercise/difficulty_level to derive a base gain from -- this fixed
# per-stat value stands in for it, sized to roughly a mid-difficulty
# exercise's own per-stat share (difficulty_level=3, split 3 ways: see
# stat_consumer's `base_gain = (difficulty_level * 0.5) / len(stat_types)`).
TEAM_TRAINING_STATS = (TargetStat.INTELLECT, TargetStat.PUCK_HANDLING, TargetStat.ON_ICE_SKATING)
TEAM_TRAINING_BASE_GAIN_PER_STAT = 0.5
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

    Also the team-day reward path: saving a TeamEventDiaryEntry for a
    TRAINING event (a note, or an explicit skip) grants the three on-ice
    stats + a fixed XP bonus once, on first save -- see
    save_diary_entry/_award_team_training_rewards. Games grant nothing
    here.

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
                f"Игра с {opponent_name} -- отметь явку",
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
        await self._push_team(team_id, "Время перенесено", f"Изменилось время {what}")
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
        await self._push_team(team_id, "Отмена", f"{what} отменена")
        is_captain = True
        sections = await self._visible_sections(event, is_captain)
        return self._to_event_read(event, sections, viewer_is_captain=is_captain)

    async def _going_members(self, event: TeamEvent) -> list[User]:
        rows = await self._events.list_attendance_for_event(event.id)
        going_ids = {row.user_id for row in rows if row.status == TeamEventAttendanceStatus.GOING}
        members = await self._teams.list_members(event.team_id)
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
        events = await self._events.list_events_for_team(team_id)
        reads = []
        for event in events:
            sections = await self._visible_sections(event, is_captain)
            reads.append(self._to_event_read(event, sections, viewer_is_captain=is_captain))
        return reads

    async def get_event(self, user: User, team_id: uuid.UUID, event_id: uuid.UUID) -> TeamEventRead:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        event = await self._get_event_or_404(event_id, team_id)
        is_captain = team.owner_id == user.id
        sections = await self._visible_sections(event, is_captain)
        return self._to_event_read(event, sections, viewer_is_captain=is_captain)

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
    ) -> TeamEventDrillRead:
        event = await self._require_captain_and_training_event(user, team_id, event_id)
        section = await self._get_section_or_404(section_id, event.id)
        order = len(await self._events.list_drills_for_section(section.id))
        drill = await self._events.create_drill(
            event.id, section.id, order, title, description, duration_minutes
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
            await self._push_team(team_id, "План тренировки готов", "Доска тренировки опубликована")
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
        event = await self._get_event_or_404(event_id, team_id)
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
        already_published = event.lineup_status == TeamEventPublishStatus.PUBLISHED
        event.lineup_status = TeamEventPublishStatus.PUBLISHED
        await self._session.commit()
        await self._session.refresh(event)
        if not already_published:
            await self._push_team(team_id, "Состав опубликован", "Тренер опубликовал состав")
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

    # -- diary / rewards --

    async def save_diary_entry(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, note: str | None
    ) -> TeamEventDiaryEntryRead:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        event = await self._get_event_or_404(event_id, team_id)
        if event.event_type != TeamEventType.TRAINING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Diary entries only apply to a training",
            )

        existing = await self._events.get_diary_entry(event.id, user.id)
        if existing is not None:
            # Editing an already-saved entry (or re-submitting the same
            # skip) never re-grants -- the reward is a first-save trigger,
            # not a per-edit one (see the model's own docstring).
            existing.note = note
            await self._session.commit()
            await self._session.refresh(existing)
            return self._to_diary_entry_read(existing)

        entry = await self._events.create_diary_entry(event.id, user.id, note)
        await self._award_team_training_rewards(user.id, event.id)
        await self._session.commit()
        await self._session.refresh(entry)
        return self._to_diary_entry_read(entry)

    async def get_diary_entry(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID
    ) -> TeamEventDiaryEntryRead | None:
        team = await self._get_team_or_404(team_id)
        await self._require_member(user, team)
        event = await self._get_event_or_404(event_id, team_id)
        entry = await self._events.get_diary_entry(event.id, user.id)
        return self._to_diary_entry_read(entry) if entry is not None else None

    async def _award_team_training_rewards(self, user_id: uuid.UUID, team_event_id: uuid.UUID) -> None:
        """Same shape as block_completed.stat_consumer's per-stat upsert
        (atomic, clamped to STAT_HARD_CAP in SQL) and xp_consumer's atomic
        XP increment + level-up check -- reused directly here rather than
        going through the outbox/block_completed event, since there's no
        Exercise/SessionBlock for this to be "about" and nothing else needs
        to react to it asynchronously; this already runs in
        save_diary_entry's own transaction.
        """
        for stat_type in TEAM_TRAINING_STATS:
            current_value = (
                await self._session.execute(
                    select(UserStat.current_value).where(
                        UserStat.user_id == user_id, UserStat.stat_type == stat_type
                    )
                )
            ).scalar_one_or_none() or 0.0
            diminishing_factor = max(0.0, 1 - current_value / STAT_HARD_CAP) ** DIMINISHING_EXPONENT
            gain = round(TEAM_TRAINING_BASE_GAIN_PER_STAT * diminishing_factor, 2)

            upsert = pg_insert(UserStat).values(
                user_id=user_id,
                stat_type=stat_type,
                current_value=gain,
                last_updated_at=datetime.now(timezone.utc),
            )
            upsert = upsert.on_conflict_do_update(
                constraint="uq_user_stats_user_stat_type",
                set_={
                    "current_value": func.least(
                        UserStat.current_value + upsert.excluded.current_value, STAT_HARD_CAP
                    ),
                    "last_updated_at": upsert.excluded.last_updated_at,
                },
            ).returning(UserStat.current_value)
            new_value = (await self._session.execute(upsert)).scalar_one()

            self._session.add(
                StatHistory(
                    user_id=user_id,
                    stat_type=stat_type,
                    value=new_value,
                    reason=f"team_training:{team_event_id}",
                )
            )

        result = await self._session.execute(
            update(User)
            .where(User.id == user_id)
            .values(xp=User.xp + TEAM_TRAINING_XP_BONUS)
            .returning(User.xp, User.level)
        )
        row = result.first()
        if row is None:
            return
        xp, level = row
        threshold = xp_to_next_level(level)
        if xp >= threshold:
            old_level = level
            level += 1
            xp -= threshold
            await self._session.execute(
                update(User).where(User.id == user_id).values(xp=xp, level=level)
            )
            OutboxRepository(self._session).add(
                LEVEL_UP_EVENT,
                {"user_id": str(user_id), "old_level": old_level, "new_level": level},
            )

    @staticmethod
    def _to_diary_entry_read(entry: TeamEventDiaryEntry) -> TeamEventDiaryEntryRead:
        return TeamEventDiaryEntryRead(
            note=entry.note, created_at=entry.created_at, updated_at=entry.updated_at
        )

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

    async def _get_event_or_404(self, event_id: uuid.UUID, team_id: uuid.UUID) -> TeamEvent:
        event = await self._events.get_event(event_id)
        if event is None or event.team_id != team_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        return event

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
        )
