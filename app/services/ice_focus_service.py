"""The focus of the day for an ice day -- see app.core.ice_focus for the
content and the choice. This only gathers the inputs: the player's on-ice
stats and what their latest recent game report asked to work on."""
import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ice_focus import ON_ICE_STATS, WORK_ON_LOOKBACK_DAYS, pick_focus
from app.models.progress import UserStat
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.repositories.schedule_repository import ScheduleRepository
from app.schemas.training_diary import IceFocusRead


class IceFocusService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def focus_for_session(self, user: User, training_session_id: uuid.UUID) -> IceFocusRead | None:
        """None for a day that isn't an ice day (games have no focus)."""
        training_session = await ScheduleRepository(self._session).get_training_session_with_owner(
            training_session_id
        )
        if training_session is None or training_session.day_plan.weekly_plan.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training session not found")
        day_plan = training_session.day_plan
        if day_plan.session_type != DaySessionType.ON_ICE:
            return None

        stats = dict(
            (
                await self._session.execute(
                    select(UserStat.stat_type, UserStat.current_value).where(
                        UserStat.user_id == user.id, UserStat.stat_type.in_(ON_ICE_STATS)
                    )
                )
            ).all()
        )
        work_on = await self._session.scalar(
            select(TrainingDiaryEntry.work_on)
            .join(TrainingSession, TrainingSession.id == TrainingDiaryEntry.training_session_id)
            .join(DayPlan, DayPlan.id == TrainingSession.day_plan_id)
            .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
            .where(
                WeeklyPlan.user_id == user.id,
                DayPlan.session_type == DaySessionType.GAME,
                DayPlan.date < day_plan.date,
                DayPlan.date >= day_plan.date - timedelta(days=WORK_ON_LOOKBACK_DAYS),
                TrainingDiaryEntry.work_on.isnot(None),
            )
            .order_by(DayPlan.date.desc())
            .limit(1)
        )
        focus, reason = pick_focus(day_plan.date.toordinal(), stats, work_on or None)
        return IceFocusRead(id=focus.id, stat=focus.stat, title=focus.title, cues=list(focus.cues), reason=reason)
