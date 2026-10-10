"""The focus of the day for an ice day -- see app.core.ice_focus for the
content and the choice. This only gathers the inputs: the player's on-ice
stats and what their latest recent game report asked to work on."""
import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.coach_tasks import CoachTaskType
from app.core.ice_focus import ON_ICE_STATS, WORK_ON_LOOKBACK_DAYS, pick_focus_with_priorities
from app.models.coach_task import WeeklyCoachTask
from app.models.progress import UserStat
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.repositories.schedule_repository import ScheduleRepository
from app.repositories.user_skill_preference_repository import UserSkillPreferenceRepository
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
        # 7.1 (2026-10-09): the coach's theme while it holds, then the
        # last game's "над чем поработать", then the priority skills.
        coach_ids = None
        until_label = None
        if user.coach_ice_focus_ids and user.coach_ice_focus_until is not None and day_plan.date <= user.coach_ice_focus_until:
            coach_ids = list(user.coach_ice_focus_ids)
            until_label = user.coach_ice_focus_until.strftime("%d.%m")
        priority = [name for _, name in await UserSkillPreferenceRepository(self._session).list_with_skill_names(user.id)]
        week_start = day_plan.date - timedelta(days=day_plan.date.weekday())
        task_focus_id = await self._session.scalar(
            select(WeeklyCoachTask.focus_id).where(
                WeeklyCoachTask.user_id == user.id,
                WeeklyCoachTask.week_start == week_start,
                WeeklyCoachTask.task_type == CoachTaskType.ICE_FOCUS.value,
                WeeklyCoachTask.focus_id.is_not(None),
                WeeklyCoachTask.claimed_at.is_(None),
            )
        )
        focus, reason = pick_focus_with_priorities(
            day_plan.date.toordinal(), stats, work_on or None, coach_ids, until_label, priority, task_focus_id
        )
        return IceFocusRead(id=focus.id, stat=focus.stat, title=focus.title, cues=list(focus.cues), reason=reason)
