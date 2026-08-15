import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.overload import MIN_FEEDBACK_SETS_FOR_SIGNAL
from app.models.schedule import DayPlan, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion, SetFeedback


class OverloadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_recent_session_feedback_counts(
        self, user_id: uuid.UUID, limit: int
    ) -> list[tuple[int, int, int]]:
        """(hard_count, max_count, total_with_feedback) for the user's most
        recent TrainingSessions that clear MIN_FEEDBACK_SETS_FOR_SIGNAL,
        newest session first (ordered by DayPlan.date, a safe total order
        here -- a date maps to at most one DayPlan per user).

        Sessions below the feedback minimum are excluded entirely by the
        HAVING clause, not returned as a low/zero row -- callers (see
        app.core.overload.classify_session) never see "no signal" as data,
        only as absence from this list.
        """
        hard_count = func.count(SetCompletion.id).filter(SetCompletion.feedback == SetFeedback.HARD)
        max_count = func.count(SetCompletion.id).filter(SetCompletion.feedback == SetFeedback.MAX)
        total_with_feedback = func.count(SetCompletion.id).filter(SetCompletion.feedback.is_not(None))

        result = await self._session.execute(
            select(hard_count, max_count, total_with_feedback)
            .select_from(TrainingSession)
            .join(DayPlan, TrainingSession.day_plan_id == DayPlan.id)
            .join(WeeklyPlan, DayPlan.weekly_plan_id == WeeklyPlan.id)
            .outerjoin(SetCompletion, SetCompletion.training_session_id == TrainingSession.id)
            .where(WeeklyPlan.user_id == user_id)
            .group_by(TrainingSession.id, DayPlan.date)
            .having(total_with_feedback >= MIN_FEEDBACK_SETS_FOR_SIGNAL)
            .order_by(DayPlan.date.desc())
            .limit(limit)
        )
        return [(row[0], row[1], row[2]) for row in result.all()]
