"""Ice and games on the muscle map (2026-10-09, release plan step 4).

The map only knew gym exercises, so after skating it showed fresh legs.
Now an ice day or a game charges ICE_SESSION_DOSE scaled by its report
(length, effort; a game is a fixed GAME_FACTOR):

- when the report is saved -- "Не был" charges nothing;
- 24 hours after the ice with no report, a default (60 medium minutes),
  from the report reminder scheduler;
- a report after the default only adds the difference (IceLoadCharge).

Each charge is aged by the time since the ice ended (recovery_factor), so
a report sent the next morning doesn't load the legs as if fresh.
"""
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.muscle_load import (
    ICE_SESSION_DOSE,
    MAX_INTENSITY,
    get_effective_muscle_load,
    ice_load_scale,
    recovery_factor,
)
from app.models.progress import IceLoadCharge, UserMuscleLoad
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.team_event import TeamEvent
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.services.report_reminder_scheduler import REPORT_DELAY, report_due_at
from app.services.week_load_service import shadow_check

DEFAULT_CHARGE_AFTER = timedelta(hours=24)


async def ice_ended_at(session: AsyncSession, day_plan: DayPlan, tz_name: str | None) -> datetime:
    """When the ice is assumed over -- the report reminder's own clock, minus
    its delay (a team event's start + typical length, else 21:00 local)."""
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    event = await session.get(TeamEvent, day_plan.team_event_id) if day_plan.team_event_id else None
    return report_due_at(day_plan, event, tz) - REPORT_DELAY


class IceLoadService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def charge(
        self,
        user_id: uuid.UUID,
        training_session_id: uuid.UUID,
        scale: float,
        ended_at: datetime,
        now: datetime | None = None,
    ) -> None:
        """Bring this session's charge to `scale`: adds (or takes back) only
        the difference from what was charged before. Doesn't commit."""
        now = now or datetime.now(timezone.utc)
        charge = (
            await self._session.execute(
                select(IceLoadCharge)
                .where(IceLoadCharge.training_session_id == training_session_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        previous = charge.scale if charge is not None else 0.0
        delta = scale - previous
        if charge is None:
            self._session.add(IceLoadCharge(training_session_id=training_session_id, user_id=user_id, scale=scale))
        else:
            charge.scale = scale
        if abs(delta) < 1e-9:
            await self._session.flush()
            return

        hours_since = max(0.0, (now - ended_at).total_seconds() / 3600)
        factor = delta * recovery_factor(hours_since)
        # Same lock order as muscle_load_consumer: sorted by muscle name.
        for muscle_group, dose in sorted(ICE_SESSION_DOSE.items(), key=lambda item: item[0].value):
            load = (
                await self._session.execute(
                    select(UserMuscleLoad)
                    .where(UserMuscleLoad.user_id == user_id, UserMuscleLoad.muscle_group == muscle_group)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            effective = get_effective_muscle_load(load, now) if load is not None else 0.0
            new_value = max(0.0, min(MAX_INTENSITY, effective + dose * factor))
            if load is None:
                if new_value > 0:
                    self._session.add(
                        UserMuscleLoad(user_id=user_id, muscle_group=muscle_group, current_value=new_value, last_updated_at=now)
                    )
            else:
                load.current_value = new_value
                load.last_updated_at = now
        await self._session.flush()


# A default older than this is dropped rather than charged late: the load
# would have recovered by now anyway.
DEFAULT_CHARGE_STALE_AFTER = timedelta(hours=72)


async def charge_default_ice_loads(session: AsyncSession, now: datetime) -> int:
    """Ice and game days whose report never came: 24 hours after the ice,
    charge 60 medium minutes (a game: GAME_FACTOR). Returns how many."""
    charged = select(IceLoadCharge.id).where(IceLoadCharge.training_session_id == TrainingSession.id).exists()
    reported = (
        select(TrainingDiaryEntry.id)
        .where(
            TrainingDiaryEntry.training_session_id == TrainingSession.id,
            TrainingDiaryEntry.reported_at.is_not(None),
        )
        .exists()
    )
    rows = (
        await session.execute(
            select(DayPlan, TrainingSession.id, User)
            .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
            .join(User, User.id == WeeklyPlan.user_id)
            .join(TrainingSession, TrainingSession.day_plan_id == DayPlan.id)
            .where(
                DayPlan.session_type.in_((DaySessionType.ON_ICE, DaySessionType.GAME)),
                DayPlan.date.between(now.date() - timedelta(days=4), now.date()),
                ~charged,
                ~reported,
            )
        )
    ).all()
    count = 0
    service = IceLoadService(session)
    for day_plan, training_session_id, user in rows:
        ended_at = await ice_ended_at(session, day_plan, user.timezone)
        if ended_at + DEFAULT_CHARGE_AFTER <= now < ended_at + DEFAULT_CHARGE_STALE_AFTER:
            scale = ice_load_scale(day_plan.session_type, None, None)
            await service.charge(user.id, training_session_id, scale, ended_at, now)
            await shadow_check(session, user.id)
            count += 1
    return count
