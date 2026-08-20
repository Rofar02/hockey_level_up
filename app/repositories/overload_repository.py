import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.overload import MIN_FEEDBACK_SETS_FOR_SIGNAL, POWER_DAY_FEEDBACK_DISCOUNT
from app.models.exercise import Exercise, StimulusType
from app.models.schedule import DayPlan, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion, SetFeedback


class OverloadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_recent_session_feedback_counts(
        self, user_id: uuid.UUID, limit: int
    ) -> list[tuple[float, float, int]]:
        """(hard_count, max_count, total_with_feedback) for the user's most
        recent TrainingSessions that clear MIN_FEEDBACK_SETS_FOR_SIGNAL,
        newest session first (ordered by DayPlan.date, a safe total order
        here -- a date maps to at most one DayPlan per user).

        Sessions below the feedback minimum are excluded entirely by the
        HAVING clause, not returned as a low/zero row -- callers (see
        app.core.overload.classify_session) never see "no signal" as data,
        only as absence from this list.

        hard_count/max_count are POWER_DAY_FEEDBACK_DISCOUNT-weighted sums,
        not plain counts (see that constant's own docstring) -- a HARD/MAX
        set on a stimulus_type=POWER exercise contributes less than a full
        1.0 toward the overload ratio. total_with_feedback is still an
        exact, undiscounted set-count.
        """
        power_weight = case(
            (Exercise.stimulus_type == StimulusType.POWER, POWER_DAY_FEEDBACK_DISCOUNT), else_=1.0
        )
        hard_count = func.coalesce(
            func.sum(power_weight).filter(SetCompletion.feedback == SetFeedback.HARD), 0.0
        )
        max_count = func.coalesce(
            func.sum(power_weight).filter(SetCompletion.feedback == SetFeedback.MAX), 0.0
        )
        total_with_feedback = func.count(SetCompletion.id).filter(SetCompletion.feedback.is_not(None))

        result = await self._session.execute(
            select(hard_count, max_count, total_with_feedback)
            .select_from(TrainingSession)
            .join(DayPlan, TrainingSession.day_plan_id == DayPlan.id)
            .join(WeeklyPlan, DayPlan.weekly_plan_id == WeeklyPlan.id)
            .outerjoin(SetCompletion, SetCompletion.training_session_id == TrainingSession.id)
            .outerjoin(Exercise, Exercise.id == SetCompletion.exercise_id)
            .where(WeeklyPlan.user_id == user_id)
            .group_by(TrainingSession.id, DayPlan.date)
            .having(total_with_feedback >= MIN_FEEDBACK_SETS_FOR_SIGNAL)
            .order_by(DayPlan.date.desc())
            .limit(limit)
        )
        return [(row[0], row[1], row[2]) for row in result.all()]
