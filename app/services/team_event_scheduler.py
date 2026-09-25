"""Background loop for the two TICK-based rows of the v2 plan's
notification table, plus stamping TeamEvent rows from active
TeamIceScheduleTemplates -- everything else (game scheduled, board/lineup
published, reschedule, cancel) is an instant push fired straight from
TeamEventService, not here. Same while-True/asyncio.sleep pattern as
reminder_scheduler.py/checkin_scheduler.py, including threading `now_utc`
explicitly through _run_tick (rather than each check calling
datetime.now() itself) so tests can pin it, same as reminder_scheduler.

1. Attendance summary to the captain, once, at the -2h deadline.
2. "Board not ready" to the captain, once, the morning of a training whose
   board is still a draft -- same 9:00-9:05 local window idiom as
   reminder_scheduler's MORNING preference, checked against the captain's
   own User.timezone (there's no team-level timezone).
3. Stamp future TeamEvent(TRAINING) rows from every active template, out
   to STAMP_WEEKS_AHEAD -- re-run every tick (cheap, and idempotent via
   TeamEventRepository.get_stamped_event), which is what keeps the
   horizon rolling forward a day at a time as real time passes, not a
   separate daily-only job.
"""
import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.push_subscription import PushSubscription
from app.models.team_event import (
    TeamEvent,
    TeamEventAttendanceStatus,
    TeamEventPublishStatus,
    TeamEventStatus,
    TeamEventType,
    TeamIceScheduleTemplate,
)
from app.models.user import User
from app.repositories.team_event_repository import TeamEventRepository
from app.repositories.team_repository import TeamRepository
from app.services.push_service import send_push

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 300

# Same -2h as TeamEventService.ATTENDANCE_DEADLINE -- not imported from
# there to avoid a scheduler -> service import for one constant; both must
# stay in sync if the deadline ever changes.
ATTENDANCE_DEADLINE = timedelta(hours=2)
_BOARD_NOT_READY_WINDOW: tuple[time, time] = (time(9, 0), time(9, 5))

ATTENDANCE_SUMMARY_TITLE = "Сводка по явке"
BOARD_NOT_READY_TITLE = "План не готов"

# How far out a template gets stamped -- long enough that a captain always
# sees several real weeks of upcoming trainings, short enough that
# deactivating a template doesn't leave months of dead rows behind it.
STAMP_WEEKS_AHEAD = 4


async def _push_user(session: AsyncSession, user_id, title: str, body: str) -> None:
    result = await session.execute(
        select(PushSubscription).where(PushSubscription.user_id == user_id)
    )
    for subscription in result.scalars().all():
        await send_push(session, subscription, title, body)


async def _due_attendance_summary_events(session: AsyncSession, now_utc: datetime) -> list[TeamEvent]:
    query = select(TeamEvent).where(
        TeamEvent.status == TeamEventStatus.SCHEDULED,
        TeamEvent.attendance_summary_sent_at.is_(None),
        TeamEvent.starts_at <= now_utc + ATTENDANCE_DEADLINE,
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def _send_attendance_summary(session: AsyncSession, event: TeamEvent, now_utc: datetime) -> None:
    teams = TeamRepository(session)
    events = TeamEventRepository(session)
    team = await teams.get_by_id(event.team_id)
    if team is None:
        return
    members = await teams.list_members(event.team_id)
    rows = await events.list_attendance_for_event(event.id)
    going = sum(1 for row in rows if row.status == TeamEventAttendanceStatus.GOING)
    not_going = sum(1 for row in rows if row.status == TeamEventAttendanceStatus.NOT_GOING)
    unmarked = len(members) - len(rows)

    what = "тренировку" if event.event_type == TeamEventType.TRAINING else "игру"
    body = f"На {what}: буду -- {going}, не буду -- {not_going}, не отметились -- {unmarked}"
    await _push_user(session, team.owner_id, ATTENDANCE_SUMMARY_TITLE, body)
    # Guards against a re-send if a slow tick overlaps the next one, same
    # idiom as DayPlan.reminder_sent_at.
    event.attendance_summary_sent_at = now_utc


async def _due_board_not_ready_events(session: AsyncSession) -> list[TeamEvent]:
    query = select(TeamEvent).where(
        TeamEvent.status == TeamEventStatus.SCHEDULED,
        TeamEvent.event_type == TeamEventType.TRAINING,
        TeamEvent.board_status == TeamEventPublishStatus.DRAFT,
        TeamEvent.board_not_ready_sent_at.is_(None),
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def _maybe_send_board_not_ready(session: AsyncSession, event: TeamEvent, now_utc: datetime) -> None:
    teams = TeamRepository(session)
    team = await teams.get_by_id(event.team_id)
    if team is None:
        return
    captain = await session.get(User, team.owner_id)
    if captain is None:
        return
    try:
        local_now = now_utc.astimezone(ZoneInfo(captain.timezone))
    except Exception:
        logger.exception(
            "Skipping board-not-ready check for team_id=%s: invalid captain timezone %r",
            team.id,
            captain.timezone,
        )
        return

    window_start, window_end = _BOARD_NOT_READY_WINDOW
    if not (window_start <= local_now.time() < window_end):
        return
    if local_now.date() != event.starts_at.astimezone(ZoneInfo(captain.timezone)).date():
        return

    await _push_user(
        session, captain.id, BOARD_NOT_READY_TITLE, "Доска тренировки на сегодня ещё не опубликована"
    )
    event.board_not_ready_sent_at = now_utc


async def _active_templates(session: AsyncSession) -> list[TeamIceScheduleTemplate]:
    result = await session.execute(
        select(TeamIceScheduleTemplate).where(TeamIceScheduleTemplate.active.is_(True))
    )
    return list(result.scalars().all())


async def _stamp_template(session: AsyncSession, template: TeamIceScheduleTemplate, now_utc: datetime) -> None:
    teams = TeamRepository(session)
    events = TeamEventRepository(session)
    team = await teams.get_by_id(template.team_id)
    if team is None:
        return
    captain = await session.get(User, team.owner_id)
    if captain is None:
        return
    try:
        captain_tz = ZoneInfo(captain.timezone)
    except Exception:
        logger.exception(
            "Skipping stamping for template_id=%s: invalid captain timezone %r",
            template.id,
            captain.timezone,
        )
        return

    local_today = now_utc.astimezone(captain_tz).date()
    horizon = local_today + timedelta(weeks=STAMP_WEEKS_AHEAD)
    for offset in range((horizon - local_today).days + 1):
        candidate_date = local_today + timedelta(days=offset)
        if candidate_date.weekday() != template.weekday:
            continue
        candidate_local = datetime.combine(candidate_date, template.start_time, tzinfo=captain_tz)
        candidate_utc = candidate_local.astimezone(timezone.utc)
        if candidate_utc <= now_utc:
            # Today's own slot, but it already started (or the exact
            # instant is now) -- don't stamp a training in the past.
            continue
        if await events.get_stamped_event(template.id, candidate_utc) is not None:
            continue
        await events.create_event(
            template.team_id,
            TeamEventType.TRAINING,
            candidate_utc,
            None,
            source_template_id=template.id,
        )


async def _run_tick(session: AsyncSession, now_utc: datetime) -> None:
    for template in await _active_templates(session):
        try:
            await _stamp_template(session, template, now_utc)
        except Exception:
            logger.exception("Stamping failed for template_id=%s", template.id)

    for event in await _due_attendance_summary_events(session, now_utc):
        try:
            await _send_attendance_summary(session, event, now_utc)
        except Exception:
            logger.exception("Attendance summary failed for team_event_id=%s", event.id)

    for event in await _due_board_not_ready_events(session):
        try:
            await _maybe_send_board_not_ready(session, event, now_utc)
        except Exception:
            logger.exception("Board-not-ready check failed for team_event_id=%s", event.id)


async def _team_event_tick() -> None:
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _run_tick(session, now_utc)


async def run_team_event_scheduler() -> None:
    while True:
        try:
            await _team_event_tick()
        except Exception:
            logger.exception("Team event scheduler tick failed")
        await asyncio.sleep(TICK_INTERVAL_SECONDS)
