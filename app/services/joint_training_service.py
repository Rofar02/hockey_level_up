"""Joint trainings with another team (2026-10-09, release plan step 3.5).

The host captain invites a team to one training or to a recurring slot;
the guest captain accepts or declines. TeamEvent.team_id stays the host:
the plan, the lineup and the event are the host captain's. The players of
an ACCEPTED guest team see the event, mark "иду / не иду" and can be put
into the lineup; for them it lands in the week like any team ice, through
the attendance mark (ScheduleService needs nothing new).

Every "who may see this event" question goes through event_team_ids /
can_see_event here -- TeamEventService._get_event_or_404(allow_guest=True)
is the one place reads use it -- so access isn't re-derived per query.
"""
import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.push_subscription import PushSubscription
from app.models.team import Team, TeamMembership
from app.models.team_event import (
    TeamEvent,
    TeamEventAttendance,
    TeamEventAttendanceStatus,
    TeamEventLineupSlot,
    TeamEventStatus,
    TeamEventType,
    TeamIceScheduleTemplate,
)
from app.models.team_event_guest import GuestTeamStatus, TeamEventGuestTeam, TeamIceTemplateGuestTeam
from app.models.user import User
from app.schemas.team_event import GuestInvitationRead, GuestTeamRead, TeamSearchHitRead
from app.services.push_service import send_push

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


async def accepted_guest_team_ids(session: AsyncSession, event_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        (
            await session.scalars(
                select(TeamEventGuestTeam.team_id).where(
                    TeamEventGuestTeam.team_event_id == event_id,
                    TeamEventGuestTeam.status == GuestTeamStatus.ACCEPTED,
                )
            )
        ).all()
    )


async def accepted_template_guest_ids(session: AsyncSession, template_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        (
            await session.scalars(
                select(TeamIceTemplateGuestTeam.team_id).where(
                    TeamIceTemplateGuestTeam.template_id == template_id,
                    TeamIceTemplateGuestTeam.status == GuestTeamStatus.ACCEPTED,
                )
            )
        ).all()
    )


async def event_team_ids(session: AsyncSession, event: TeamEvent) -> list[uuid.UUID]:
    """The host first, then every accepted guest team."""
    return [event.team_id, *await accepted_guest_team_ids(session, event.id)]


async def can_see_event(session: AsyncSession, team_id: uuid.UUID, event: TeamEvent) -> bool:
    """`team_id` (the team in the URL) may open `event`: it is the host or
    an accepted guest."""
    return team_id in await event_team_ids(session, event)


async def joint_event_ids_for_team(session: AsyncSession, team_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        (
            await session.scalars(
                select(TeamEventGuestTeam.team_event_id).where(
                    TeamEventGuestTeam.team_id == team_id,
                    TeamEventGuestTeam.status == GuestTeamStatus.ACCEPTED,
                )
            )
        ).all()
    )


async def _push_users(session: AsyncSession, user_ids: list[uuid.UUID], title: str, body: str) -> None:
    if not user_ids:
        return
    subscriptions = (await session.scalars(select(PushSubscription).where(PushSubscription.user_id.in_(user_ids)))).all()
    for subscription in subscriptions:
        await send_push(session, subscription, title, body)


class JointTrainingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- search --

    async def search_teams(self, user: User, team_id: uuid.UUID, query: str) -> list[TeamSearchHitRead]:
        """Teams to invite, by name or city -- never the caller's own."""
        await self._captain_team(user, team_id)
        text = " ".join(query.split())
        if len(text) < 2:
            return []
        pattern = f"%{text}%"
        teams = (
            await self._session.scalars(
                select(Team)
                .where(Team.id != team_id, or_(Team.name.ilike(pattern), Team.city.ilike(pattern)))
                .order_by(Team.name)
                .limit(10)
            )
        ).all()
        from app.core import leagues

        return [
            TeamSearchHitRead(
                id=team.id,
                name=team.name,
                logo_url=team.logo_url,
                city=team.city,
                league_name=leagues.league_display_name(team.league_code, team.league_other_name),
                division_name=leagues.division_display_name(team.league_code, team.division_code),
            )
            for team in teams
        ]

    # -- invitations: host side --

    async def invite_to_event(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, guest_team_id: uuid.UUID
    ) -> GuestTeamRead:
        host = await self._captain_team(user, team_id)
        event = await self._session.get(TeamEvent, event_id)
        if event is None or event.team_id != host.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        if event.event_type != TeamEventType.TRAINING or event.status != TeamEventStatus.SCHEDULED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пригласить можно только на тренировку")
        if event.starts_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Тренировка уже прошла")
        guest = await self._guest_team_or_404(host, guest_team_id)
        row = await self._session.scalar(
            select(TeamEventGuestTeam).where(
                TeamEventGuestTeam.team_event_id == event.id, TeamEventGuestTeam.team_id == guest.id
            )
        )
        if row is None:
            row = TeamEventGuestTeam(team_event_id=event.id, team_id=guest.id, status=GuestTeamStatus.INVITED)
            self._session.add(row)
        elif row.status == GuestTeamStatus.DECLINED:
            row.status = GuestTeamStatus.INVITED
            row.decided_at = None
        await self._session.flush()
        when = event.starts_at.astimezone(ZoneInfo(user.timezone or "UTC")).strftime("%d.%m %H:%M")
        await _push_users(
            self._session, [guest.owner_id], "Совместная тренировка", f"«{host.name}» зовут вас на тренировку {when}"
        )
        await self._session.commit()
        return GuestTeamRead(team_id=guest.id, name=guest.name, logo_url=guest.logo_url, status=row.status)

    async def invite_to_template(
        self, user: User, team_id: uuid.UUID, template_id: uuid.UUID, guest_team_id: uuid.UUID
    ) -> GuestTeamRead:
        host = await self._captain_team(user, team_id)
        template = await self._session.get(TeamIceScheduleTemplate, template_id)
        if template is None or template.team_id != host.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        guest = await self._guest_team_or_404(host, guest_team_id)
        row = await self._session.scalar(
            select(TeamIceTemplateGuestTeam).where(
                TeamIceTemplateGuestTeam.template_id == template.id, TeamIceTemplateGuestTeam.team_id == guest.id
            )
        )
        if row is None:
            row = TeamIceTemplateGuestTeam(template_id=template.id, team_id=guest.id, status=GuestTeamStatus.INVITED)
            self._session.add(row)
        elif row.status == GuestTeamStatus.DECLINED:
            row.status = GuestTeamStatus.INVITED
            row.decided_at = None
        await self._session.flush()
        slot = f"{WEEKDAYS[template.weekday]} {template.start_time.strftime('%H:%M')}"
        await _push_users(
            self._session, [guest.owner_id], "Совместные тренировки", f"«{host.name}» зовут вас тренироваться вместе: {slot}"
        )
        await self._session.commit()
        return GuestTeamRead(team_id=guest.id, name=guest.name, logo_url=guest.logo_url, status=row.status)

    async def list_event_guests(self, user: User, team_id: uuid.UUID, event_id: uuid.UUID) -> list[GuestTeamRead]:
        """Who else trains here -- any participant of the event sees it."""
        event = await self._session.get(TeamEvent, event_id)
        if event is None or not await can_see_event(self._session, team_id, event):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        if await self._session.scalar(
            select(TeamMembership.id).where(TeamMembership.team_id == team_id, TeamMembership.user_id == user.id)
        ) is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this team")
        rows = (
            await self._session.execute(
                select(TeamEventGuestTeam, Team)
                .join(Team, Team.id == TeamEventGuestTeam.team_id)
                .where(TeamEventGuestTeam.team_event_id == event.id)
                .order_by(Team.name)
            )
        ).all()
        host = await self._session.get(Team, event.team_id)
        reads = [GuestTeamRead(team_id=host.id, name=host.name, logo_url=host.logo_url, status="host")]
        reads += [
            GuestTeamRead(team_id=team.id, name=team.name, logo_url=team.logo_url, status=row.status)
            for row, team in rows
            if row.status != GuestTeamStatus.DECLINED or event.team_id == team_id
        ]
        return reads

    # -- invitations: guest side --

    async def list_incoming(self, user: User, team_id: uuid.UUID) -> list[GuestInvitationRead]:
        team = await self._captain_team(user, team_id)
        now = datetime.now(timezone.utc)
        reads: list[GuestInvitationRead] = []
        event_rows = (
            await self._session.execute(
                select(TeamEventGuestTeam, TeamEvent, Team)
                .join(TeamEvent, TeamEvent.id == TeamEventGuestTeam.team_event_id)
                .join(Team, Team.id == TeamEvent.team_id)
                .where(
                    TeamEventGuestTeam.team_id == team.id,
                    TeamEventGuestTeam.status == GuestTeamStatus.INVITED,
                    TeamEvent.status == TeamEventStatus.SCHEDULED,
                    TeamEvent.starts_at > now,
                )
                .order_by(TeamEvent.starts_at)
            )
        ).all()
        for row, event, host in event_rows:
            reads.append(
                GuestInvitationRead(
                    id=row.id, kind="event", host_team_id=host.id, host_team_name=host.name,
                    host_logo_url=host.logo_url, starts_at=event.starts_at,
                    conflict=await self._own_training_same_day(team, event) is not None,
                )
            )
        template_rows = (
            await self._session.execute(
                select(TeamIceTemplateGuestTeam, TeamIceScheduleTemplate, Team)
                .join(TeamIceScheduleTemplate, TeamIceScheduleTemplate.id == TeamIceTemplateGuestTeam.template_id)
                .join(Team, Team.id == TeamIceScheduleTemplate.team_id)
                .where(TeamIceTemplateGuestTeam.team_id == team.id, TeamIceTemplateGuestTeam.status == GuestTeamStatus.INVITED)
            )
        ).all()
        for row, template, host in template_rows:
            reads.append(
                GuestInvitationRead(
                    id=row.id, kind="slot", host_team_id=host.id, host_team_name=host.name,
                    host_logo_url=host.logo_url,
                    slot_label=f"{WEEKDAYS[template.weekday]} {template.start_time.strftime('%H:%M')}",
                    conflict=False,
                )
            )
        return reads

    async def answer(
        self, user: User, team_id: uuid.UUID, invitation_id: uuid.UUID, accept: bool, replace_own: bool = False
    ) -> GuestTeamRead:
        """Accept or decline an invitation (to one training or to a slot).
        Only a pending invitation to a training that is still ahead can be
        answered (409 otherwise). Accepting a training on a day the team
        already has its own one: 409 "conflict" unless replace_own -- then
        the own one is cancelled, so nobody gets two ice sessions in one
        day. A slot can also be declined after accepting it: the team
        leaves the slot and its trainings ahead."""
        team = await self._captain_team(user, team_id)
        row = await self._session.get(TeamEventGuestTeam, invitation_id)
        if row is not None and row.team_id == team.id:
            event = await self._session.get(TeamEvent, row.team_event_id)
            if row.status != GuestTeamStatus.INVITED:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Приглашение уже не действует")
            if event.status != TeamEventStatus.SCHEDULED or event.starts_at <= datetime.now(timezone.utc):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Тренировка уже прошла или отменена")
            if accept:
                own = await self._own_training_same_day(team, event)
                if own is not None and not replace_own:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")
                if own is not None:
                    from app.services.team_event_service import TeamEventService

                    await TeamEventService(self._session).cancel_event(user, team.id, own.id)
                row.status = GuestTeamStatus.ACCEPTED
                members = await self._member_ids(team.id)
                await _push_users(self._session, [m for m in members if m != user.id], "Совместная тренировка", "В расписании новая совместная тренировка — отметьтесь «Иду»")
            else:
                await self._drop_guest_players(event, team.id)
                row.status = GuestTeamStatus.DECLINED
            row.decided_at = datetime.now(timezone.utc)
            await self._session.commit()
            return GuestTeamRead(team_id=team.id, name=team.name, logo_url=team.logo_url, status=row.status)

        slot_row = await self._session.get(TeamIceTemplateGuestTeam, invitation_id)
        if slot_row is None or slot_row.team_id != team.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
        if slot_row.status == GuestTeamStatus.DECLINED or (accept and slot_row.status != GuestTeamStatus.INVITED):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Приглашение уже не действует")
        slot_row.status = GuestTeamStatus.ACCEPTED if accept else GuestTeamStatus.DECLINED
        slot_row.decided_at = datetime.now(timezone.utc)
        future = (
            await self._session.scalars(
                select(TeamEvent).where(
                    TeamEvent.source_template_id == slot_row.template_id,
                    TeamEvent.status == TeamEventStatus.SCHEDULED,
                    TeamEvent.starts_at > datetime.now(timezone.utc),
                )
            )
        ).all()
        for event in future:
            if accept:
                # Already stamped trainings of the slot become joint too.
                await self.add_accepted_guest(event, team.id)
            else:
                # Leaving the slot takes the team out of its trainings ahead.
                await self._drop_guest_team(event, team.id)
        await self._session.commit()
        return GuestTeamRead(team_id=team.id, name=team.name, logo_url=team.logo_url, status=slot_row.status)

    async def leave(self, user: User, team_id: uuid.UUID, event_id: uuid.UUID) -> None:
        """The guest captain takes the team out of a joint training: it
        disappears for their players."""
        team = await self._captain_team(user, team_id)
        row = await self._session.scalar(
            select(TeamEventGuestTeam).where(
                TeamEventGuestTeam.team_event_id == event_id, TeamEventGuestTeam.team_id == team.id
            )
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
        event = await self._session.get(TeamEvent, event_id)
        self._require_ahead(event)
        await self._drop_guest_players(event, team.id)
        row.status = GuestTeamStatus.DECLINED
        row.decided_at = datetime.now(timezone.utc)
        await self._session.commit()

    async def remove_guest(
        self, user: User, team_id: uuid.UUID, event_id: uuid.UUID, guest_team_id: uuid.UUID
    ) -> None:
        """The host captain takes a guest team (invited or accepted) out of
        their training."""
        host = await self._captain_team(user, team_id)
        event = await self._session.get(TeamEvent, event_id)
        if event is None or event.team_id != host.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        self._require_ahead(event)
        if not await self._drop_guest_team(event, guest_team_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        guest = await self._session.get(Team, guest_team_id)
        if guest is not None:
            await _push_users(
                self._session, [guest.owner_id], "Совместная тренировка", f"«{host.name}» убрали вашу команду из тренировки"
            )
        await self._session.commit()

    async def _drop_guest_team(self, event: TeamEvent, guest_team_id: uuid.UUID) -> bool:
        """Mark the team's row for this event DECLINED and take its players
        out. False when the team was never on it. Doesn't commit."""
        row = await self._session.scalar(
            select(TeamEventGuestTeam).where(
                TeamEventGuestTeam.team_event_id == event.id, TeamEventGuestTeam.team_id == guest_team_id
            )
        )
        if row is None or row.status == GuestTeamStatus.DECLINED:
            return row is not None
        await self._drop_guest_players(event, guest_team_id)
        row.status = GuestTeamStatus.DECLINED
        row.decided_at = datetime.now(timezone.utc)
        return True

    async def add_accepted_guest(self, event: TeamEvent, guest_team_id: uuid.UUID) -> None:
        """For stamping: a training from a slot with an accepted guest team
        is joint from the start. Doesn't commit."""
        exists = await self._session.scalar(
            select(TeamEventGuestTeam.id).where(
                TeamEventGuestTeam.team_event_id == event.id, TeamEventGuestTeam.team_id == guest_team_id
            )
        )
        if exists is None:
            self._session.add(
                TeamEventGuestTeam(
                    team_event_id=event.id, team_id=guest_team_id, status=GuestTeamStatus.ACCEPTED,
                    decided_at=datetime.now(timezone.utc),
                )
            )
            await self._session.flush()

    # -- helpers --

    @staticmethod
    def _require_ahead(event: TeamEvent) -> None:
        """A training that already started (or was cancelled) keeps who was
        on it -- its marks are the attendance history."""
        if event.status != TeamEventStatus.SCHEDULED or event.starts_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Тренировка уже прошла или отменена")

    async def _captain_team(self, user: User, team_id: uuid.UUID) -> Team:
        team = await self._session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        if team.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the team captain can do this")
        return team

    async def _guest_team_or_404(self, host: Team, guest_team_id: uuid.UUID) -> Team:
        guest = await self._session.get(Team, guest_team_id)
        if guest is None or guest.id == host.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        return guest

    async def _member_ids(self, team_id: uuid.UUID) -> list[uuid.UUID]:
        return list(
            (await self._session.scalars(select(TeamMembership.user_id).where(TeamMembership.team_id == team_id))).all()
        )

    async def _own_training_same_day(self, team: Team, event: TeamEvent) -> TeamEvent | None:
        """The guest team's own training on the joint one's day (in the
        guest captain's time zone) -- the "two ice sessions" trap."""
        captain = await self._session.get(User, team.owner_id)
        tz = ZoneInfo((captain.timezone if captain else None) or "UTC")
        day = event.starts_at.astimezone(tz).date()
        day_start = datetime.combine(day, time.min, tzinfo=tz)
        return await self._session.scalar(
            select(TeamEvent)
            .where(
                TeamEvent.team_id == team.id,
                TeamEvent.event_type == TeamEventType.TRAINING,
                TeamEvent.status == TeamEventStatus.SCHEDULED,
                TeamEvent.starts_at >= day_start,
                TeamEvent.starts_at < day_start + timedelta(days=1),
            )
            .order_by(TeamEvent.starts_at)
            .limit(1)
        )

    async def _drop_guest_players(self, event: TeamEvent, guest_team_id: uuid.UUID) -> None:
        """The joint training leaves the guest team's players' weeks, and
        their marks and their places in its lines are removed."""
        from app.services.schedule_service import ScheduleService

        member_ids = await self._member_ids(guest_team_id)
        rows = (
            await self._session.scalars(
                select(TeamEventAttendance).where(
                    TeamEventAttendance.team_event_id == event.id, TeamEventAttendance.user_id.in_(member_ids)
                )
            )
        ).all()
        schedule = ScheduleService(self._session)
        for row in rows:
            if row.status == TeamEventAttendanceStatus.GOING:
                player = await self._session.get(User, row.user_id)
                if player is not None:
                    await schedule.revert_team_event_days(player, event.id)
            await self._session.delete(row)
        if member_ids:
            await self._session.execute(
                delete(TeamEventLineupSlot).where(
                    TeamEventLineupSlot.team_event_id == event.id, TeamEventLineupSlot.user_id.in_(member_ids)
                )
            )
        await self._session.flush()
