import uuid
from datetime import datetime
from datetime import time as time_

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team_event import (
    TeamEvent,
    TeamEventAbsenceReason,
    TeamEventAttendance,
    TeamEventAttendanceStatus,
    TeamEventDiaryEntry,
    TeamEventDrill,
    TeamEventLineupGroup,
    TeamEventLineupSlot,
    TeamEventPublishStatus,
    TeamEventStatus,
    TeamEventType,
    TeamIceScheduleTemplate,
)


class TeamEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- TeamEvent --

    async def create_event(
        self,
        team_id: uuid.UUID,
        event_type: TeamEventType,
        starts_at: datetime,
        opponent_name: str | None,
        source_template_id: uuid.UUID | None = None,
    ) -> TeamEvent:
        event = TeamEvent(
            team_id=team_id,
            event_type=event_type,
            starts_at=starts_at,
            opponent_name=opponent_name,
            source_template_id=source_template_id,
            # Games have no board at all (see TeamEvent's docstring) --
            # board_status stays None rather than an unused DRAFT default.
            board_status=(
                TeamEventPublishStatus.DRAFT if event_type == TeamEventType.TRAINING else None
            ),
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def get_stamped_event(
        self, source_template_id: uuid.UUID, starts_at: datetime
    ) -> TeamEvent | None:
        """The stamping job's own idempotency check -- see
        team_event_scheduler._stamp_template. starts_at is deterministically
        re-derived from (template.weekday, template.start_time, the
        captain's timezone) on every tick, so an exact match is a safe key:
        it can never coincidentally collide with a different intended slot.
        """
        result = await self._session.execute(
            select(TeamEvent).where(
                TeamEvent.source_template_id == source_template_id,
                TeamEvent.starts_at == starts_at,
            )
        )
        return result.scalar_one_or_none()

    async def get_event(self, event_id: uuid.UUID) -> TeamEvent | None:
        return await self._session.get(TeamEvent, event_id)

    async def list_events_for_team(self, team_id: uuid.UUID) -> list[TeamEvent]:
        result = await self._session.execute(
            select(TeamEvent)
            .where(TeamEvent.team_id == team_id, TeamEvent.status == TeamEventStatus.SCHEDULED)
            .order_by(TeamEvent.starts_at)
        )
        return list(result.scalars().all())

    # -- TeamEventDrill --

    async def create_drill(
        self, team_event_id: uuid.UUID, order: int, title: str, description: str | None
    ) -> TeamEventDrill:
        drill = TeamEventDrill(
            team_event_id=team_event_id, order=order, title=title, description=description
        )
        self._session.add(drill)
        await self._session.flush()
        return drill

    async def get_drill(self, drill_id: uuid.UUID) -> TeamEventDrill | None:
        return await self._session.get(TeamEventDrill, drill_id)

    async def list_drills_for_event(self, team_event_id: uuid.UUID) -> list[TeamEventDrill]:
        result = await self._session.execute(
            select(TeamEventDrill)
            .where(TeamEventDrill.team_event_id == team_event_id)
            .order_by(TeamEventDrill.order)
        )
        return list(result.scalars().all())

    async def next_drill_order(self, team_event_id: uuid.UUID) -> int:
        # len() rather than MAX(order)+1: reorder_drills below always
        # renumbers the full set densely from 0, so the count is always
        # exactly the next free slot -- no gaps a MAX could skip past.
        result = await self._session.execute(
            select(TeamEventDrill.id).where(TeamEventDrill.team_event_id == team_event_id)
        )
        return len(result.all())

    async def delete_drill(self, drill: TeamEventDrill) -> None:
        await self._session.delete(drill)
        await self._session.flush()

    # -- TeamEventAttendance --

    async def get_attendance(
        self, team_event_id: uuid.UUID, user_id: uuid.UUID
    ) -> TeamEventAttendance | None:
        result = await self._session.execute(
            select(TeamEventAttendance).where(
                TeamEventAttendance.team_event_id == team_event_id,
                TeamEventAttendance.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_attendance_for_event(
        self, team_event_id: uuid.UUID
    ) -> list[TeamEventAttendance]:
        result = await self._session.execute(
            select(TeamEventAttendance).where(TeamEventAttendance.team_event_id == team_event_id)
        )
        return list(result.scalars().all())

    async def upsert_attendance(
        self,
        team_event_id: uuid.UUID,
        user_id: uuid.UUID,
        status: TeamEventAttendanceStatus,
        reason: TeamEventAbsenceReason | None,
        reason_note: str | None,
    ) -> TeamEventAttendance:
        attendance = await self.get_attendance(team_event_id, user_id)
        if attendance is None:
            attendance = TeamEventAttendance(
                team_event_id=team_event_id,
                user_id=user_id,
                status=status,
                reason=reason,
                reason_note=reason_note,
            )
            self._session.add(attendance)
        else:
            attendance.status = status
            attendance.reason = reason
            attendance.reason_note = reason_note
        await self._session.flush()
        return attendance

    async def delete_attendance(self, attendance: TeamEventAttendance) -> None:
        await self._session.delete(attendance)
        await self._session.flush()

    # -- TeamEventLineupGroup / TeamEventLineupSlot --

    async def create_lineup_group(
        self, team_event_id: uuid.UUID, order: int, name: str | None, color: str | None
    ) -> TeamEventLineupGroup:
        group = TeamEventLineupGroup(
            team_event_id=team_event_id, order=order, name=name, color=color
        )
        self._session.add(group)
        await self._session.flush()
        return group

    async def get_lineup_group(self, group_id: uuid.UUID) -> TeamEventLineupGroup | None:
        return await self._session.get(TeamEventLineupGroup, group_id)

    async def list_lineup_groups_for_event(
        self, team_event_id: uuid.UUID
    ) -> list[TeamEventLineupGroup]:
        result = await self._session.execute(
            select(TeamEventLineupGroup)
            .where(TeamEventLineupGroup.team_event_id == team_event_id)
            .order_by(TeamEventLineupGroup.order)
        )
        return list(result.scalars().all())

    async def next_lineup_group_order(self, team_event_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(TeamEventLineupGroup.id).where(
                TeamEventLineupGroup.team_event_id == team_event_id
            )
        )
        return len(result.all())

    async def delete_lineup_group(self, group: TeamEventLineupGroup) -> None:
        await self._session.delete(group)
        await self._session.flush()

    async def get_lineup_slot(
        self, team_event_id: uuid.UUID, user_id: uuid.UUID
    ) -> TeamEventLineupSlot | None:
        result = await self._session.execute(
            select(TeamEventLineupSlot).where(
                TeamEventLineupSlot.team_event_id == team_event_id,
                TeamEventLineupSlot.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_lineup_slots_for_event(
        self, team_event_id: uuid.UUID
    ) -> list[TeamEventLineupSlot]:
        result = await self._session.execute(
            select(TeamEventLineupSlot).where(TeamEventLineupSlot.team_event_id == team_event_id)
        )
        return list(result.scalars().all())

    async def upsert_lineup_slot(
        self, team_event_id: uuid.UUID, group_id: uuid.UUID, user_id: uuid.UUID
    ) -> TeamEventLineupSlot:
        slot = await self.get_lineup_slot(team_event_id, user_id)
        if slot is None:
            slot = TeamEventLineupSlot(
                team_event_id=team_event_id, group_id=group_id, user_id=user_id
            )
            self._session.add(slot)
        else:
            slot.group_id = group_id
        await self._session.flush()
        return slot

    async def delete_lineup_slot(self, slot: TeamEventLineupSlot) -> None:
        await self._session.delete(slot)
        await self._session.flush()

    # -- TeamEventDiaryEntry --

    async def get_diary_entry(
        self, team_event_id: uuid.UUID, user_id: uuid.UUID
    ) -> TeamEventDiaryEntry | None:
        result = await self._session.execute(
            select(TeamEventDiaryEntry).where(
                TeamEventDiaryEntry.team_event_id == team_event_id,
                TeamEventDiaryEntry.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_diary_entry(
        self, team_event_id: uuid.UUID, user_id: uuid.UUID, note: str | None
    ) -> TeamEventDiaryEntry:
        entry = TeamEventDiaryEntry(team_event_id=team_event_id, user_id=user_id, note=note)
        self._session.add(entry)
        await self._session.flush()
        return entry

    # -- TeamIceScheduleTemplate --

    async def create_template(
        self, team_id: uuid.UUID, weekday: int, start_time: time_
    ) -> TeamIceScheduleTemplate:
        template = TeamIceScheduleTemplate(team_id=team_id, weekday=weekday, start_time=start_time)
        self._session.add(template)
        await self._session.flush()
        return template

    async def get_template(self, template_id: uuid.UUID) -> TeamIceScheduleTemplate | None:
        return await self._session.get(TeamIceScheduleTemplate, template_id)

    async def list_templates_for_team(self, team_id: uuid.UUID) -> list[TeamIceScheduleTemplate]:
        result = await self._session.execute(
            select(TeamIceScheduleTemplate)
            .where(TeamIceScheduleTemplate.team_id == team_id)
            .order_by(TeamIceScheduleTemplate.weekday, TeamIceScheduleTemplate.start_time)
        )
        return list(result.scalars().all())

    async def list_active_templates(self) -> list[TeamIceScheduleTemplate]:
        result = await self._session.execute(
            select(TeamIceScheduleTemplate).where(TeamIceScheduleTemplate.active.is_(True))
        )
        return list(result.scalars().all())

    async def delete_template(self, template: TeamIceScheduleTemplate) -> None:
        await self._session.delete(template)
        await self._session.flush()
