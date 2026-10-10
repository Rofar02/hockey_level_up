"""«Как прошёл день» (2026-10-10, owner's request): one report for a whole
day -- every training of it (a double day's two), the gym's exercises with
their sets, reps and weights, the ice / game report, the muscles the day
loaded and the stats it moved.

The muscle numbers use the same units as the muscle map: a completed gym
block adds difficulty x GAIN_PER_DIFFICULTY_LEVEL x its weight per muscle
(muscle_load_consumer's formula), an ice day what its charge really put on
(IceLoadCharge.applied). Summed for the day, capped at the map's 10 -- what
this day did, not the map's current (decayed) state.
"""
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.ice_focus import FOCUS_BY_ID
from app.core.muscle_load import GAIN_PER_DIFFICULTY_LEVEL, ICE_SESSION_DOSE, MAX_INTENSITY
from app.models.exercise import ExerciseMuscleGroup
from app.models.progress import IceLoadCharge, StatHistory
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.schemas.day_report import (
    DayReportExerciseRead,
    DayReportIceRead,
    DayReportMuscleRead,
    DayReportRead,
    DayReportSetRead,
    DayReportStatRead,
    DayReportTrainingRead,
)


def _local_zone(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone or "UTC")
    except Exception:
        return ZoneInfo("UTC")


class DayReportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def report(self, user: User, day: date) -> DayReportRead:
        plans = (
            await self._session.scalars(
                select(DayPlan)
                .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
                .where(WeeklyPlan.user_id == user.id, DayPlan.date == day)
                .options(
                    selectinload(DayPlan.training_session)
                    .selectinload(TrainingSession.blocks)
                    .selectinload(SessionBlock.exercise)
                )
            )
        ).all()
        if not plans:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="На этот день нет плана")
        # Morning first, then the main day, then the evening.
        order = {"morning": 0, None: 1, "evening": 2}
        plans = sorted(plans, key=lambda plan: order.get(plan.time_of_day, 1))

        muscles: dict[str, float] = defaultdict(float)
        trainings = []
        for plan in plans:
            if plan.session_type == DaySessionType.REST or plan.training_session is None:
                trainings.append(
                    DayReportTrainingRead(day_plan_id=plan.id, session_type=plan.session_type, time_of_day=plan.time_of_day)
                )
                continue
            trainings.append(await self._training(plan, muscles))

        return DayReportRead(
            date=day,
            trainings=trainings,
            muscles=[
                DayReportMuscleRead(muscle_group=group, intensity=round(min(MAX_INTENSITY, value), 2))
                for group, value in sorted(muscles.items(), key=lambda item: -item[1])
                if value > 0.05
            ],
            stats=await self._stats(user, day),
            sets_total=sum(t.sets_total for t in trainings),
            tonnage_kg=round(sum(t.tonnage_kg for t in trainings), 1),
            exercises_done=sum(t.exercises_done for t in trainings),
        )

    async def _training(self, plan: DayPlan, muscles: dict[str, float]) -> DayReportTrainingRead:
        session = plan.training_session
        blocks = sorted(session.blocks, key=lambda block: block.order)
        sets = (
            await self._session.scalars(
                select(SetCompletion)
                .where(SetCompletion.training_session_id == session.id)
                .order_by(SetCompletion.set_number)
            )
        ).all()
        sets_by_exercise: dict[uuid.UUID, list[SetCompletion]] = defaultdict(list)
        for entry in sets:
            sets_by_exercise[entry.exercise_id].append(entry)

        done_blocks = [block for block in blocks if block.completed_at is not None]
        weights = (
            await self._session.execute(
                select(ExerciseMuscleGroup.exercise_id, ExerciseMuscleGroup.muscle_group, ExerciseMuscleGroup.weight).where(
                    ExerciseMuscleGroup.exercise_id.in_([block.exercise_id for block in done_blocks] or [uuid.uuid4()])
                )
            )
        ).all()
        by_exercise: dict[uuid.UUID, list[tuple[str, float]]] = defaultdict(list)
        for exercise_id, group, weight in weights:
            by_exercise[exercise_id].append((str(group), weight))
        for block in done_blocks:
            for group, weight in by_exercise[block.exercise_id]:
                muscles[group] += block.exercise.difficulty_level * GAIN_PER_DIFFICULTY_LEVEL * weight

        exercises = []
        for block in blocks:
            logged = sets_by_exercise.get(block.exercise_id, [])
            exercises.append(
                DayReportExerciseRead(
                    name=block.exercise.name,
                    phase=block.phase,
                    done=block.completed_at is not None,
                    skipped=block.skipped_at is not None,
                    sets=[
                        DayReportSetRead(
                            weight_kg=entry.weight_kg,
                            reps=entry.reps_completed,
                            seconds=entry.duration_seconds_completed,
                        )
                        for entry in logged
                    ],
                    feedback=next((entry.feedback for entry in reversed(logged) if entry.feedback is not None), None),
                )
            )

        times = [moment for block in blocks for moment in (block.completed_at, block.skipped_at) if moment is not None]
        minutes = (
            max(1, round((max(times) - min(times)).total_seconds() / 60)) if len(times) >= 2 else None
        )

        ice = None
        if plan.session_type in (DaySessionType.ON_ICE, DaySessionType.GAME):
            ice = await self._ice(session.id)
            charge = await self._session.scalar(
                select(IceLoadCharge).where(IceLoadCharge.training_session_id == session.id)
            )
            if charge is not None:
                applied = charge.applied or {
                    muscle.value: dose * charge.scale for muscle, dose in ICE_SESSION_DOSE.items()
                }
                for group, amount in applied.items():
                    muscles[group] += amount

        return DayReportTrainingRead(
            day_plan_id=plan.id,
            session_type=plan.session_type,
            time_of_day=plan.time_of_day,
            team_event_id=plan.team_event_id,
            exercises_done=len(done_blocks),
            exercises_total=len(blocks),
            sets_total=len(sets),
            tonnage_kg=round(
                sum((entry.weight_kg or 0) * (entry.reps_completed or 0) for entry in sets), 1
            ),
            minutes=minutes,
            exercises=exercises,
            ice=ice,
        )

    async def _ice(self, training_session_id: uuid.UUID) -> DayReportIceRead | None:
        entry = await self._session.scalar(
            select(TrainingDiaryEntry).where(TrainingDiaryEntry.training_session_id == training_session_id)
        )
        if entry is None or entry.reported_at is None:
            return None
        focus = FOCUS_BY_ID.get(entry.focus_id or "")
        return DayReportIceRead(
            skipped=entry.skipped,
            duration_minutes=entry.duration_minutes,
            effort=entry.effort,
            focus_title=focus.title if focus is not None else None,
            focus_result=entry.focus_result,
            game_result=entry.game_result,
            goals=entry.goals,
            assists=entry.assists,
            note=entry.note,
        )

    async def _stats(self, user: User, day: date) -> list[DayReportStatRead]:
        """Each stat the day moved: its last value before the day and at its
        end, in the player's own time zone."""
        zone = _local_zone(user)
        start = datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc)
        end = start + timedelta(days=1)
        rows = (
            await self._session.execute(
                select(StatHistory.stat_type, StatHistory.value, StatHistory.recorded_at)
                .where(StatHistory.user_id == user.id, StatHistory.recorded_at < end)
                .order_by(StatHistory.recorded_at)
            )
        ).all()
        before: dict[str, float] = {}
        after: dict[str, float] = {}
        for stat, value, at in rows:
            if at < start:
                before[str(stat)] = value
            else:
                after[str(stat)] = value
        result = []
        for stat, value in after.items():
            gain = value - before.get(stat, value)
            if abs(gain) >= 0.05:
                result.append(DayReportStatRead(stat=stat, before=round(before.get(stat, value), 1), after=round(value, 1)))
        return sorted(result, key=lambda item: item.before - item.after)
