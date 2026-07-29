import itertools
import random
from collections import defaultdict
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.session_templates import get_phase_split
from app.models.exercise import Exercise, ExerciseCategory, TargetStat, TrainingPhase
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.user import User
from app.repositories.exercise_repository import ExerciseRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.schemas.exercise import ExerciseRead
from app.schemas.schedule import (
    DayPlanRead,
    SessionBlockRead,
    TrainingSessionRead,
    WeeklyPlanCreate,
    WeeklyPlanRead,
)

_SESSION_TYPE_TO_CATEGORY = {
    DaySessionType.ON_ICE: ExerciseCategory.ON_ICE,
    DaySessionType.OFF_ICE: ExerciseCategory.OFF_ICE,
}


class ScheduleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._exercises = ExerciseRepository(session)
        self._schedule = ScheduleRepository(session)

    async def create_weekly_plan(self, user: User, payload: WeeklyPlanCreate) -> WeeklyPlanRead:
        dates = [day.date for day in payload.days]
        if len(set(dates)) != len(dates):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate dates in weekly plan"
            )

        weekly_plan = WeeklyPlan(user_id=user.id, week_start_date=min(dates))
        for day_in in payload.days:
            day_plan = DayPlan(date=day_in.date, session_type=day_in.session_type)
            if day_in.session_type != DaySessionType.REST:
                day_plan.training_session = await self._build_training_session(
                    day_in.session_type, user
                )
            weekly_plan.day_plans.append(day_plan)

        try:
            await self._schedule.save(weekly_plan)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Weekly plan already exists for this week",
            ) from exc

        saved = await self._schedule.get_by_id_with_details(weekly_plan.id)
        return self._to_read_schema(saved)

    async def get_current_weekly_plan(self, user: User) -> WeeklyPlanRead:
        weekly_plan = await self._schedule.get_current(user.id, date.today())
        if weekly_plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No current weekly plan"
            )
        return self._to_read_schema(weekly_plan)

    async def _build_training_session(
        self, session_type: DaySessionType, user: User
    ) -> TrainingSession:
        category = _SESSION_TYPE_TO_CATEGORY[session_type]
        blocks: list[SessionBlock] = []

        warmup = await self._pick_single(TrainingPhase.WARMUP, user)
        if warmup is not None:
            blocks.append(SessionBlock(phase=TrainingPhase.WARMUP, exercise_id=warmup.id, order=0))

        main_exercises = await self._pick_main(category, user)
        for i, exercise in enumerate(main_exercises):
            blocks.append(SessionBlock(phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=i))

        cooldown = await self._pick_single(TrainingPhase.COOLDOWN, user)
        if cooldown is not None:
            blocks.append(
                SessionBlock(phase=TrainingPhase.COOLDOWN, exercise_id=cooldown.id, order=0)
            )

        return TrainingSession(blocks=blocks)

    async def _pick_single(self, phase: TrainingPhase, user: User) -> Exercise | None:
        """Warmup/cooldown: curated pool for the phase, filtered only by equipment -- no category filter."""
        candidates = await self._exercises.list(phase=phase, equipment_type=user.equipment_access)
        if not candidates:
            return None
        return random.choice(candidates)

    async def _pick_main(self, category: ExerciseCategory, user: User) -> list[Exercise]:
        """Main: 2-3 exercises for the day's category, round-robin across the 4 target stats."""
        candidates = await self._exercises.list(
            category=category, phase=TrainingPhase.MAIN, equipment_type=user.equipment_access
        )
        if not candidates:
            return []

        count = random.randint(2, 3)

        by_stat: dict[TargetStat, list[Exercise]] = defaultdict(list)
        for exercise in candidates:
            by_stat[exercise.target_stat].append(exercise)
        for pool in by_stat.values():
            random.shuffle(pool)

        picked: list[Exercise] = []
        empty_streak = 0
        for stat in itertools.cycle(TargetStat):
            if len(picked) >= count or empty_streak >= len(TargetStat):
                break
            pool = by_stat.get(stat)
            if pool:
                picked.append(pool.pop())
                empty_streak = 0
            else:
                empty_streak += 1
        return picked

    @staticmethod
    def _to_read_schema(weekly_plan: WeeklyPlan) -> WeeklyPlanRead:
        day_reads = []
        for day in weekly_plan.day_plans:
            session_read = None
            if day.training_session is not None:
                category = _SESSION_TYPE_TO_CATEGORY[day.session_type]
                blocks_read = [
                    SessionBlockRead(
                        phase=block.phase,
                        order=block.order,
                        exercise=ExerciseRead.model_validate(block.exercise),
                    )
                    for block in day.training_session.blocks
                ]
                session_read = TrainingSessionRead(
                    id=day.training_session.id,
                    phase_split=get_phase_split(category),
                    blocks=blocks_read,
                )
            day_reads.append(
                DayPlanRead(
                    id=day.id,
                    date=day.date,
                    session_type=day.session_type,
                    training_session=session_read,
                )
            )
        return WeeklyPlanRead(
            id=weekly_plan.id, week_start_date=weekly_plan.week_start_date, day_plans=day_reads
        )
