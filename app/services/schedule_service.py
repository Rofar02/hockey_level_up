import random
from collections import defaultdict
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.session_templates import get_phase_split
from app.core.training_block import (
    DIFFICULTY_PRIORITY_PREDICATES,
    MAIN_EXERCISE_COUNT_RANGE,
    BlockPhase,
    get_phase,
)
from app.models.exercise import Exercise, ExerciseCategory, TargetStat, TrainingPhase
from app.models.schedule import (
    DayPlan,
    DaySessionType,
    SessionBlock,
    TrainingBlock,
    TrainingSession,
    WeeklyPlan,
)
from app.models.user import User
from app.repositories.exercise_repository import ExerciseRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.repositories.skill_repository import SkillRepository
from app.repositories.training_block_repository import TrainingBlockRepository
from app.repositories.user_skill_preference_repository import UserSkillPreferenceRepository
from app.schemas.exercise import ExerciseRead
from app.schemas.schedule import (
    DayPlanRead,
    ScheduleConflictRead,
    SessionBlockRead,
    TrainingSessionRead,
    WeeklyPlanCreate,
    WeeklyPlanPatch,
    WeeklyPlanPatchResult,
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
        self._skills = SkillRepository(session)
        self._user_skill_preferences = UserSkillPreferenceRepository(session)
        self._training_blocks = TrainingBlockRepository(session)

    async def create_weekly_plan(self, user: User, payload: WeeklyPlanCreate) -> WeeklyPlanRead:
        dates = [day.date for day in payload.days]
        if len(set(dates)) != len(dates):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate dates in weekly plan"
            )

        training_block = await self._resolve_training_block(user)
        block_phase = get_phase(training_block.week_in_block)

        weekly_plan = WeeklyPlan(
            user_id=user.id, week_start_date=min(dates), training_block_id=training_block.id
        )
        for day_in in payload.days:
            day_plan = DayPlan(date=day_in.date, session_type=day_in.session_type)
            if day_in.session_type != DaySessionType.REST:
                day_plan.training_session = await self._build_training_session(
                    day_in.session_type, user, block_phase
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

    async def patch_current_weekly_plan(
        self, user: User, payload: WeeklyPlanPatch
    ) -> WeeklyPlanPatchResult:
        """Edit specific days of the already-declared current week in place.

        Per-date, not all-or-nothing: a date whose day already has a
        completed SessionBlock is left untouched and reported in
        `conflicts` instead of failing the whole request -- the caller may
        be trying to fix a typo on Wednesday in the same request that also
        (accidentally) includes Monday, which is already underway.
        """
        dates = [day.date for day in payload.days]
        if len(set(dates)) != len(dates):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate dates in patch"
            )

        weekly_plan = await self._schedule.get_current(user.id, date.today())
        if weekly_plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No current weekly plan"
            )

        week_end = weekly_plan.week_start_date + timedelta(days=6)
        day_plans_by_date = {day_plan.date: day_plan for day_plan in weekly_plan.day_plans}
        block_phase = await self._block_phase_for_weekly_plan(weekly_plan)

        conflicts: list[ScheduleConflictRead] = []
        for day_in in payload.days:
            if not (weekly_plan.week_start_date <= day_in.date <= week_end):
                conflicts.append(
                    ScheduleConflictRead(date=day_in.date, detail="Дата вне текущей недели")
                )
                continue

            day_plan = day_plans_by_date.get(day_in.date)
            if day_plan is None or self._has_completed_block(day_plan):
                conflicts.append(
                    ScheduleConflictRead(
                        date=day_in.date, detail="Этот день уже начат, нельзя изменить"
                    )
                )
                continue

            day_plan.session_type = day_in.session_type
            if day_plan.training_session is not None:
                # Explicit delete + flush *before* attaching a replacement --
                # TrainingSession.day_plan_id is unique, and simply
                # reassigning the relationship would rely on the ORM
                # ordering this row's DELETE before the new row's INSERT
                # within the same flush, which SQLAlchemy does not
                # guarantee (inserts/updates are flushed before deletes).
                await self._session.delete(day_plan.training_session)
                await self._session.flush()
                day_plan.training_session = None

            if day_in.session_type != DaySessionType.REST:
                day_plan.training_session = await self._build_training_session(
                    day_in.session_type, user, block_phase
                )

        await self._session.commit()
        saved = await self._schedule.get_by_id_with_details(weekly_plan.id)
        return WeeklyPlanPatchResult(
            weekly_plan=self._to_read_schema(saved), conflicts=conflicts
        )

    async def _block_phase_for_weekly_plan(self, weekly_plan: WeeklyPlan) -> BlockPhase:
        block = None
        if weekly_plan.training_block_id is not None:
            block = await self._training_blocks.get_by_id(weekly_plan.training_block_id)
        # No block on record (shouldn't happen via any current code path) --
        # fall back to the same baseline a brand-new block starts at.
        return get_phase(block.week_in_block) if block is not None else get_phase(1)

    @staticmethod
    def _has_completed_block(day_plan: DayPlan) -> bool:
        if day_plan.training_session is None:
            return False
        return any(block.completed_at is not None for block in day_plan.training_session.blocks)

    async def _resolve_training_block(self, user: User) -> TrainingBlock:
        """Advance (or start) the user's periodization block for this week's plan.

        A block's `week_in_block` is mutated in place while it's < 4. Hitting
        4 (a just-completed deload week) retires it and starts a new block
        at block_number + 1 -- that specific transition is also what flags
        the user for a norm-test retake (border of a mesocycle is where the
        concept doc says a retest is "honest": not exhausted, not stale).
        """
        active = await self._training_blocks.get_active_for_user(user.id)
        if active is None:
            return await self._training_blocks.create(
                TrainingBlock(user_id=user.id, block_number=1, week_in_block=1)
            )

        if active.week_in_block < 4:
            active.week_in_block += 1
            return active

        user.suggested_reassessment = True
        return await self._training_blocks.create(
            TrainingBlock(user_id=user.id, block_number=active.block_number + 1, week_in_block=1)
        )

    async def _build_training_session(
        self, session_type: DaySessionType, user: User, block_phase: BlockPhase
    ) -> TrainingSession:
        category = _SESSION_TYPE_TO_CATEGORY[session_type]
        blocks: list[SessionBlock] = []

        warmup = await self._pick_single(TrainingPhase.WARMUP, category, user, block_phase)
        if warmup is not None:
            blocks.append(SessionBlock(phase=TrainingPhase.WARMUP, exercise_id=warmup.id, order=0))

        main_exercises = await self._pick_main(category, user, block_phase)
        for i, exercise in enumerate(main_exercises):
            blocks.append(SessionBlock(phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=i))

        cooldown = await self._pick_single(TrainingPhase.COOLDOWN, category, user, block_phase)
        if cooldown is not None:
            blocks.append(
                SessionBlock(phase=TrainingPhase.COOLDOWN, exercise_id=cooldown.id, order=0)
            )

        return TrainingSession(blocks=blocks)

    async def _pick_single(
        self,
        phase: TrainingPhase,
        category: ExerciseCategory,
        user: User,
        block_phase: BlockPhase,
    ) -> Exercise | None:
        """Warmup/cooldown: curated pool for the phase, filtered by the day's category.

        equipment_access still narrows off_ice candidates but never excludes
        on_ice ones (no equipment choice on the ice). The active block's
        phase biases difficulty (intensification prefers difficulty>=4,
        deload prefers difficulty<=2), falling back to the full pool when
        nothing matches that preference -- never an empty result just
        because the preferred difficulty band is missing.
        """
        candidates = await self._exercises.list_for_assembly(
            phase=phase, equipment_access=user.equipment_access, category=category
        )
        if not candidates:
            return None

        difficulty_predicate = DIFFICULTY_PRIORITY_PREDICATES.get(block_phase)
        if difficulty_predicate is not None:
            candidates = [e for e in candidates if difficulty_predicate(e)] or candidates

        return random.choice(candidates)

    async def _pick_main(
        self, category: ExerciseCategory, user: User, block_phase: BlockPhase
    ) -> list[Exercise]:
        """Main: up to 2-3 exercises (1-2 on a deload week) for the day's
        category, at most one per target stat.

        If fewer than `count` stats have candidates, returns fewer exercises
        rather than repeating a stat. Two priority layers apply *within*
        each stat's candidate pool, in this order:

          1. block-phase difficulty preference (intensification: >=4,
             deload: <=2) -- narrows the pool for that stat, falling back to
             the full stat pool if nothing matches;
          2. SkillTag priority for the user's chosen skills (Phase 7) --
             narrows *that* pool further, again falling back if nothing
             matches.

        Difficulty goes first because it's the block's physiological
        constraint on the week (how hard this week should be, chosen by the
        system); SkillTag is the user's personalization on top, and should
        only pick among whatever difficulty envelope the block allows --
        otherwise a user's skill choice could quietly cancel out
        intensification/deload by always winning with an off-envelope
        exercise. A user with no preferences and an accumulation-phase block
        (no difficulty predicate) sees plain round-robin, identical to
        before this and the Phase 7 priority were added.
        """
        candidates = await self._exercises.list_for_assembly(
            phase=TrainingPhase.MAIN, equipment_access=user.equipment_access, category=category
        )
        if not candidates:
            return []

        count_min, count_max = MAIN_EXERCISE_COUNT_RANGE[block_phase]
        count = random.randint(count_min, count_max)

        preferred_skill_ids = await self._user_skill_preferences.list_skill_ids_for_user(user.id)
        priority_exercise_ids = await self._skills.list_tagged_exercise_ids(
            exercise_ids=[exercise.id for exercise in candidates], skill_ids=preferred_skill_ids
        )
        difficulty_predicate = DIFFICULTY_PRIORITY_PREDICATES.get(block_phase)

        by_stat: dict[TargetStat, list[Exercise]] = defaultdict(list)
        for exercise in candidates:
            by_stat[exercise.target_stat].append(exercise)

        picked: list[Exercise] = []
        for stat in TargetStat:
            if len(picked) >= count:
                break
            stat_pool = by_stat.get(stat)
            if not stat_pool:
                continue

            if difficulty_predicate is not None:
                stat_pool = [e for e in stat_pool if difficulty_predicate(e)] or stat_pool

            skill_pool = [e for e in stat_pool if e.id in priority_exercise_ids] or stat_pool
            picked.append(random.choice(skill_pool))
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
                        id=block.id,
                        phase=block.phase,
                        order=block.order,
                        completed_at=block.completed_at,
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
