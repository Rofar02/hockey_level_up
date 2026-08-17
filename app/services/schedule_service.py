import logging
import random
import uuid
from collections import defaultdict
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.session_duration import compute_phase_split, estimate_session_duration_seconds
from app.core.training_block import (
    DIFFICULTY_PRIORITY_PREDICATES,
    effective_difficulty_cap,
    is_final_taper_week,
    is_tapering,
    main_exercise_count_range,
    max_difficulty_for_level,
)
from app.models.exercise import (
    EquipmentType,
    Exercise,
    ExerciseCategory,
    MovementPattern,
    TargetStat,
    TrainingPhase,
    UserMovementPatternVariant,
)
from app.models.schedule import (
    BlockPhase,
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
from app.repositories.user_movement_pattern_variant_repository import (
    UserMovementPatternVariantRepository,
)
from app.repositories.user_skill_preference_repository import UserSkillPreferenceRepository
from app.schemas.exercise import exercise_to_read
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
from app.services.overload_service import OverloadService
from app.services.training_block_service import TrainingBlockService

logger = logging.getLogger(__name__)

_SESSION_TYPE_TO_CATEGORY = {
    DaySessionType.ON_ICE: ExerciseCategory.ON_ICE,
    DaySessionType.OFF_ICE: ExerciseCategory.OFF_ICE,
}

# suggest_party_exercises-only: what equipment_type values a member with this
# equipment_access can actually train with, as cumulative capability rather
# than list_for_assembly's single-user exact match -- see that method's
# docstring for why the two need different rules.
_EQUIPMENT_REACH: dict[EquipmentType, frozenset[EquipmentType]] = {
    EquipmentType.GYM: frozenset({EquipmentType.GYM, EquipmentType.HOME, EquipmentType.BODYWEIGHT}),
    EquipmentType.HOME: frozenset({EquipmentType.HOME, EquipmentType.BODYWEIGHT}),
    EquipmentType.BODYWEIGHT: frozenset({EquipmentType.BODYWEIGHT}),
}


class ScheduleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._exercises = ExerciseRepository(session)
        self._schedule = ScheduleRepository(session)
        self._skills = SkillRepository(session)
        self._user_skill_preferences = UserSkillPreferenceRepository(session)
        self._variants = UserMovementPatternVariantRepository(session)
        self._training_block_service = TrainingBlockService(session)
        self._overload_service = OverloadService(session)

    async def create_weekly_plan(self, user: User, payload: WeeklyPlanCreate) -> WeeklyPlanRead:
        dates = [day.date for day in payload.days]
        if len(set(dates)) != len(dates):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate dates in weekly plan"
            )

        target_week_start_date = min(dates)
        training_block = await self._training_block_service.get_or_create_and_resolve(user.id)
        block_phase = await self._overload_service.apply_brakes(user, training_block.phase)

        weekly_plan = WeeklyPlan(
            user_id=user.id, week_start_date=target_week_start_date, training_block_id=training_block.id
        )
        for day_in in payload.days:
            day_plan = DayPlan(
                date=day_in.date,
                session_type=day_in.session_type,
                on_ice_minutes=day_in.on_ice_minutes,
            )
            if day_in.session_type != DaySessionType.REST:
                day_plan.training_session = await self._build_session_for_day(
                    day_in.session_type, user, block_phase, training_block
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
        return await self._to_read_schema(saved)

    async def get_current_weekly_plan(self, user: User) -> WeeklyPlanRead:
        weekly_plan = await self._schedule.get_current(user.id, date.today())
        if weekly_plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No current weekly plan"
            )
        return await self._to_read_schema(weekly_plan)

    async def get_weekly_plan(self, user: User, week_start_date: date | None) -> WeeklyPlanRead:
        """GET /schedule/weekly -- week_start_date is optional and aliases to
        get_current_weekly_plan when absent, so callers who don't care which
        week (the common case) see byte-identical behavior to
        /schedule/weekly/current. When given, this is a direct
        (user, week_start_date) lookup, not a "which week is today inside"
        range check -- a 404 here means that specific week was never
        declared, which is a different fact than "no current plan" and gets
        a distinct detail message so the two aren't confused on the client.
        """
        if week_start_date is None:
            return await self.get_current_weekly_plan(user)

        weekly_plan = await self._schedule.get_by_week_start_date(user.id, week_start_date)
        if weekly_plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No weekly plan for week starting {week_start_date.isoformat()}",
            )
        return await self._to_read_schema(weekly_plan)

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
        return await self._patch_weekly_plan(user, payload, week_start_date=None)

    async def patch_weekly_plan(
        self, user: User, payload: WeeklyPlanPatch, week_start_date: date | None
    ) -> WeeklyPlanPatchResult:
        """PATCH /schedule/weekly -- same optional-week_start_date aliasing as
        get_weekly_plan; None behaves exactly like patch_current_weekly_plan
        (which now delegates here too, so there's exactly one place this
        logic lives)."""
        return await self._patch_weekly_plan(user, payload, week_start_date)

    async def _patch_weekly_plan(
        self, user: User, payload: WeeklyPlanPatch, week_start_date: date | None
    ) -> WeeklyPlanPatchResult:
        dates = [day.date for day in payload.days]
        if len(set(dates)) != len(dates):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate dates in patch"
            )

        if week_start_date is None:
            weekly_plan = await self._schedule.get_current(user.id, date.today())
            not_found_detail = "No current weekly plan"
        else:
            weekly_plan = await self._schedule.get_by_week_start_date(user.id, week_start_date)
            not_found_detail = f"No weekly plan for week starting {week_start_date.isoformat()}"

        if weekly_plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)

        week_end = weekly_plan.week_start_date + timedelta(days=6)
        day_plans_by_date = {day_plan.date: day_plan for day_plan in weekly_plan.day_plans}
        training_block = await self._training_block_for_weekly_plan(weekly_plan)
        block_phase = await self._overload_service.apply_brakes(
            user, training_block.phase if training_block is not None else BlockPhase.ACCUMULATION
        )

        conflicts: list[ScheduleConflictRead] = []
        for day_in in payload.days:
            if not (weekly_plan.week_start_date <= day_in.date <= week_end):
                # Wording deliberately generic ("plan's week", not "current
                # week") -- this method now also serves patch_weekly_plan for
                # an arbitrary week, where "текущей" would be wrong.
                conflicts.append(
                    ScheduleConflictRead(date=day_in.date, detail="Дата вне недели плана")
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
            day_plan.on_ice_minutes = day_in.on_ice_minutes
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
                day_plan.training_session = await self._build_session_for_day(
                    day_in.session_type, user, block_phase, training_block
                )

        await self._session.commit()
        saved = await self._schedule.get_by_id_with_details(weekly_plan.id)
        return WeeklyPlanPatchResult(
            weekly_plan=await self._to_read_schema(saved), conflicts=conflicts
        )

    async def _training_block_for_weekly_plan(self, weekly_plan: WeeklyPlan) -> TrainingBlock | None:
        """Read-only: whatever block this week is already tied to.
        Deliberately doesn't call TrainingBlockService.resolve_active_block --
        patching a specific (possibly past or future) week shouldn't reach
        past that week's own block to catch up whatever the globally
        *active* block is doing; only declaring a brand-new week
        (create_weekly_plan) does that.

        None (shouldn't happen via any current code path) means no block on
        record -- callers fall back to the same baseline a brand-new block
        starts at (BlockPhase.ACCUMULATION), and variant rotation (Phase:
        П.3) is simply skipped for this call since there's no block_number
        to version a pin against.
        """
        if weekly_plan.training_block_id is None:
            return None
        return await self._training_block_service.get_by_id(weekly_plan.training_block_id)

    @staticmethod
    def _has_completed_block(day_plan: DayPlan) -> bool:
        if day_plan.training_session is None:
            return False
        return any(block.completed_at is not None for block in day_plan.training_session.blocks)

    async def _build_session_for_day(
        self,
        session_type: DaySessionType,
        user: User,
        block_phase: BlockPhase,
        training_block: TrainingBlock | None = None,
        *,
        today: date | None = None,
    ) -> TrainingSession:
        """Dispatch to the GAME-day builder (light activation only) or the
        regular on/off-ice builder -- the single place both
        create_weekly_plan and _patch_weekly_plan go through, so neither
        has to know GAME is a special case.

        training_block (Phase: П.3) and today (Phase: П.5, tournament
        taper) are only ever consumed by the regular builder's _pick_main
        -- GAME days have no MAIN block at all, so _build_game_day_session
        doesn't need either.
        """
        if session_type == DaySessionType.GAME:
            return await self._build_game_day_session(user, block_phase)
        return await self._build_training_session(
            session_type, user, block_phase, training_block, today=today
        )

    async def _build_game_day_session(self, user: User, block_phase: BlockPhase) -> TrainingSession:
        """GAME day: light pre-game activation only -- no main block (no full
        workout right before a game) and no cooldown (a game follows, not
        recovery). GAME has no ExerciseCategory of its own (unlike
        ON_ICE/OFF_ICE), so physical activation is pulled from both the
        on-ice and off-ice warmup pools instead of picking one, plus one
        optional intellect-targeted warmup exercise for mental prep.
        """
        blocks: list[SessionBlock] = []
        for category in (ExerciseCategory.ON_ICE, ExerciseCategory.OFF_ICE):
            activation = await self._pick_single(
                TrainingPhase.WARMUP, category, user, block_phase, suitable_for_game_day=True
            )
            if activation is not None:
                blocks.append(
                    SessionBlock(phase=TrainingPhase.WARMUP, exercise_id=activation.id, order=len(blocks))
                )

        picked_ids = {block.exercise_id for block in blocks}
        mental_prep = await self._pick_mental_prep(user, exclude_ids=picked_ids)
        if mental_prep is not None:
            blocks.append(
                SessionBlock(phase=TrainingPhase.WARMUP, exercise_id=mental_prep.id, order=len(blocks))
            )

        return TrainingSession(blocks=blocks)

    async def _pick_mental_prep(
        self, user: User, *, exclude_ids: set[uuid.UUID]
    ) -> Exercise | None:
        """One optional warmup exercise targeting intellect, for a GAME day's
        mental prep. The catalog may not have any such exercise yet -- that's
        fine, this returns None rather than raising, so GAME sessions still
        build with physical activation only until content catches up.
        """
        candidates = await self._exercises.list_for_assembly(
            phase=TrainingPhase.WARMUP, equipment_access=user.equipment_access
        )
        # "INTELLECT anywhere among its target_stats", not just the primary
        # one -- this is a point lookup for a specific need, not the
        # diversity-bucketing mechanism _pick_main/suggest_party_exercises use.
        intellect_ids = await self._exercises.list_exercise_ids_with_stat(
            [e.id for e in candidates], TargetStat.INTELLECT
        )
        candidates = [e for e in candidates if e.id in intellect_ids and e.id not in exclude_ids]
        if not candidates:
            return None

        candidates = self._apply_level_cap(candidates, user, context="game/mental_prep")
        return random.choice(candidates)

    async def _build_training_session(
        self,
        session_type: DaySessionType,
        user: User,
        block_phase: BlockPhase,
        training_block: TrainingBlock | None = None,
        *,
        today: date | None = None,
    ) -> TrainingSession:
        """MAIN is picked first and warmup/cooldown are chosen retrospectively
        to match it (Phase 3) -- storage order of `blocks` is still
        warmup/main/cooldown, only the *decision* order changed, so this
        picks main before appending anything, then builds `blocks` in the
        original display order once every pick is known.
        """
        category = _SESSION_TYPE_TO_CATEGORY[session_type]

        main_exercises = await self._pick_main(
            category, user, block_phase, training_block=training_block, today=today
        )
        main_patterns = await self._movement_patterns_union(
            [exercise.id for exercise in main_exercises]
        )

        warmup = await self._pick_single(
            TrainingPhase.WARMUP, category, user, block_phase, preferred_patterns=main_patterns
        )
        cooldown = await self._pick_single(
            TrainingPhase.COOLDOWN, category, user, block_phase, preferred_patterns=main_patterns
        )

        # order runs across the whole session, not reset per phase (same
        # len(blocks) idiom _build_game_day_session already uses below) --
        # resetting it per phase left every session with warmup/main[0]/
        # cooldown all sharing order=0, which made TrainingSession.blocks'
        # order_by="SessionBlock.order" (a single global sort) fall back to
        # whatever tiebreak order the DB happened to return them in instead
        # of the intended warmup-then-main-then-cooldown sequence.
        blocks: list[SessionBlock] = []
        if warmup is not None:
            blocks.append(SessionBlock(phase=TrainingPhase.WARMUP, exercise_id=warmup.id, order=len(blocks)))

        for exercise in main_exercises:
            blocks.append(SessionBlock(phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=len(blocks)))

        if cooldown is not None:
            blocks.append(
                SessionBlock(phase=TrainingPhase.COOLDOWN, exercise_id=cooldown.id, order=len(blocks))
            )

        return TrainingSession(blocks=blocks)

    async def _movement_patterns_union(self, exercise_ids: list[uuid.UUID]) -> set[MovementPattern]:
        by_exercise = await self._exercises.list_movement_patterns_by_exercise(exercise_ids)
        return {pattern for patterns in by_exercise.values() for pattern in patterns}

    async def _pick_single(
        self,
        phase: TrainingPhase,
        category: ExerciseCategory,
        user: User,
        block_phase: BlockPhase,
        *,
        suitable_for_game_day: bool | None = None,
        preferred_patterns: set[MovementPattern] | None = None,
    ) -> Exercise | None:
        """Warmup/cooldown: curated pool for the phase, filtered by the day's category.

        equipment_access still narrows off_ice candidates but never excludes
        on_ice ones (no equipment choice on the ice). User.level caps which
        difficulty tier is even eligible (see _apply_level_cap), and *then*
        the active block's phase biases difficulty within whatever that cap
        allows (intensification prefers difficulty>=4, deload prefers
        difficulty<=2), falling back to the level-capped pool when nothing
        matches that preference -- never an empty result just because the
        preferred difficulty band is missing.

        preferred_patterns (Phase 3) narrows the pool once more, last, to
        exercises sharing at least one movement_pattern with the session's
        already-picked MAIN exercises -- same fallback shape as every layer
        above it: if nothing in the level/difficulty-narrowed pool overlaps,
        fall back to that pool untouched rather than picking from outside
        it. None/empty (GAME-day activation, which has no MAIN to match)
        skips this layer entirely.

        suitable_for_game_day is None for every regular on/off-ice call --
        only _build_game_day_session passes True, to keep its physical
        activation pick to exercises actually marked light enough for it
        (see Exercise.suitable_for_game_day), not the full WARMUP pool.
        """
        candidates = await self._exercises.list_for_assembly(
            phase=phase,
            equipment_access=user.equipment_access,
            category=category,
            suitable_for_game_day=suitable_for_game_day,
        )
        if not candidates:
            return None

        candidates = self._apply_level_cap(candidates, user, context=f"{phase}/{category}")

        difficulty_predicate = DIFFICULTY_PRIORITY_PREDICATES.get(block_phase)
        if difficulty_predicate is not None:
            candidates = [e for e in candidates if difficulty_predicate(e)] or candidates

        if preferred_patterns:
            patterns_by_id = await self._exercises.list_movement_patterns_by_exercise(
                [e.id for e in candidates]
            )
            matched = [
                e
                for e in candidates
                if preferred_patterns.intersection(patterns_by_id.get(e.id, ()))
            ]
            candidates = matched or candidates

        return random.choice(candidates)

    async def _pick_main(
        self,
        category: ExerciseCategory,
        user: User,
        block_phase: BlockPhase,
        *,
        training_block: TrainingBlock | None = None,
        today: date | None = None,
    ) -> list[Exercise]:
        """Main: up to 5-6 exercises in accumulation, 4-5 in intensification,
        3-4 on a deload week (see MAIN_EXERCISE_COUNT_RANGE) for the day's
        category, at most one per movement_pattern (an exercise can be
        tagged with more than one pattern -- see ExerciseMovementPattern,
        a plain membership tag with no "primary" -- so once an exercise is
        picked it's excluded from every other pattern's pool too, not just
        the one that picked it).

        This used to bucket by each exercise's *primary* target_stat
        instead. Off-ice exercises only ever have 4 possible primary stats
        (strength/agility/intellect/endurance -- on_ice_skating/
        puck_handling are on-ice-only), which made 4 a hard ceiling on an
        off-ice main block no matter what MAIN_EXERCISE_COUNT_RANGE said.
        movement_pattern has 10 values and 94% of the off-ice MAIN catalog
        is tagged, so the configured count is actually reachable now.
        target_stat keeps being used for XP/reward attribution
        (stat_consumer reads every row, not just a "primary" one) -- it
        just stopped being the axis that limits how many exercises get
        picked.

        Patterns are shuffled before iterating (unlike target_stat's old
        fixed enum order, which barely mattered across only 4 buckets but
        would otherwise always favor the same first 5-6 of 10 patterns
        every single session). If fewer than `count` patterns have
        candidates, returns fewer exercises rather than repeating one.
        Three priority layers apply *within* each pattern's candidate pool,
        in this order:

          1. User.level difficulty cap (see _apply_level_cap) -- the hard
             ceiling on what the user is allowed at all, falling back to the
             full stat pool (ignoring the cap, with a warning) only if the
             stat has literally nothing under it;
          2. block-phase difficulty preference (intensification: >=4,
             deload: <=2) -- narrows the level-capped pool further, falling
             back to it if nothing matches;
          3. SkillTag priority for the user's chosen skills (Phase 7) --
             narrows *that* pool further, again falling back if nothing
             matches.

        Level goes first because it's a hard capability gate, not a
        preference -- every later layer's fallback lands on *its* pool, so
        none of them can ever reintroduce an over-cap exercise except layer
        1's own last-resort fallback. Difficulty preference goes next
        because it's the block's physiological constraint on the week (how
        hard this week should be, chosen by the system); SkillTag is the
        user's personalization on top. A user with no preferences and an
        accumulation-phase block (no difficulty predicate) sees plain
        round-robin among their level-capped pool, identical to before this
        and the Phase 7 priority were added.

        On top of those three, _apply_muscle_balance does one more
        tie-break *within* whatever the SkillTag layer left: it avoids a
        third pick in a row sharing the same off_ice muscle_group, but never
        widens the pool back out to do so -- so SkillTag priority still wins
        any real conflict between the two.

        Before any of those three layers even run, variant stability
        (Phase: П.3) can short-circuit a pattern's pick entirely: if the
        user already has a UserMovementPatternVariant pinned for this
        (category, pattern) and it's still in the level/difficulty-narrowed
        pool, it's reused as-is for as long as `training_block` hasn't
        crossed to a new block_number -- double progression (П.1) works
        better on a stable exercise than one that changes every session.
        Crossing into a fresh, non-macrocycle-deload block deliberately
        excludes the outgoing variant from the pool before the three
        priority layers run, guaranteeing an actual change rather than
        leaving it to chance; crossing into a macrocycle-deload block
        (П.2) holds the old variant instead of rotating -- a recovery
        block isn't the moment to introduce something new -- and just
        bumps the pin's block_number bookmark so rotation resumes at the
        next real boundary. training_block=None (e.g. patching a week
        whose block record is missing) skips this layer entirely, same as
        before this feature existed.

        The count range itself can also be tightened before any of this
        runs (Phase: П.4 seasonal mode) -- during the user's chosen
        SEASON/PLAYOFFS period, off-ice volume is capped lower even in
        accumulation, see app.core.training_block.main_exercise_count_range.

        A user-set tournament_date (Phase: П.5 taper) overrides
        season_period outright, on the same axis, for the final
        TAPER_WINDOW_WEEKS before it -- see
        app.core.training_block.is_tapering/is_final_taper_week. today
        defaults to date.today() for every real caller, injectable purely
        for deterministic tests/simulation, same shape as
        TrainingBlockService.resolve_active_block's own `today` param.
        """
        candidates = await self._exercises.list_for_assembly(
            phase=TrainingPhase.MAIN, equipment_access=user.equipment_access, category=category
        )
        if not candidates:
            return []

        resolved_today = today or date.today()
        count_min, count_max = main_exercise_count_range(
            block_phase,
            category=category,
            season_period=user.season_period,
            is_tapering=is_tapering(resolved_today, user.tournament_date),
            is_final_taper_week=is_final_taper_week(resolved_today, user.tournament_date),
        )
        count = random.randint(count_min, count_max)

        preferred_skill_ids = await self._user_skill_preferences.list_skill_ids_for_user(user.id)
        priority_exercise_ids = await self._skills.list_tagged_exercise_ids(
            exercise_ids=[exercise.id for exercise in candidates], skill_ids=preferred_skill_ids
        )
        difficulty_predicate = DIFFICULTY_PRIORITY_PREDICATES.get(block_phase)
        level_cap = max_difficulty_for_level(user.level)

        # Bucketed by *every* movement_pattern an exercise is tagged with
        # (membership, not a "primary" one -- ExerciseMovementPattern has no
        # order column, unlike ExerciseTargetStat). An exercise with no
        # patterns at all (not yet tagged) is simply absent from every
        # bucket.
        patterns_by_exercise = await self._exercises.list_movement_patterns_by_exercise(
            [exercise.id for exercise in candidates]
        )
        by_pattern: dict[MovementPattern, list[Exercise]] = defaultdict(list)
        for exercise in candidates:
            for pattern in patterns_by_exercise.get(exercise.id, ()):
                by_pattern[pattern].append(exercise)

        # Phase: П.3 variant stability -- one bulk fetch per call, keyed by
        # pattern, mirroring priority_exercise_ids/patterns_by_exercise above.
        existing_pins: dict[MovementPattern, UserMovementPatternVariant] = {}
        if training_block is not None:
            existing_pins = await self._variants.list_for_user_category(user.id, category)

        picked: list[Exercise] = []
        picked_ids: set[uuid.UUID] = set()
        patterns = list(MovementPattern)
        random.shuffle(patterns)
        for pattern in patterns:
            if len(picked) >= count:
                break
            # A multi-tagged exercise can appear under more than one
            # pattern's bucket -- exclude whatever's already picked so the
            # same exercise never fills two slots in one main block.
            pattern_pool = [e for e in by_pattern.get(pattern, ()) if e.id not in picked_ids]
            if not pattern_pool:
                continue

            pattern_pool = self._apply_level_cap(
                pattern_pool, user, context=f"main/{category}/{pattern}", level_cap=level_cap
            )

            if difficulty_predicate is not None:
                pattern_pool = [e for e in pattern_pool if difficulty_predicate(e)] or pattern_pool

            existing_pin = existing_pins.get(pattern)
            pinned_exercise = None
            if existing_pin is not None:
                pinned_exercise = next(
                    (e for e in pattern_pool if e.id == existing_pin.exercise_id), None
                )

            use_pin = False
            if pinned_exercise is not None:
                same_block = existing_pin.block_number == training_block.block_number
                hold_through_deload = training_block.is_macrocycle_deload
                use_pin = same_block or hold_through_deload

            if use_pin:
                choice = pinned_exercise
                if existing_pin.block_number != training_block.block_number:
                    # Deload-hold: keep the variant, just bump the bookmark
                    # so rotation resumes at the next non-deload boundary.
                    existing_pin.block_number = training_block.block_number
            else:
                stat_pool = pattern_pool
                # A real rotation boundary (not a first-ever pin, not a
                # deload-hold) -- exclude the outgoing variant so the
                # change is guaranteed, not just possible by luck.
                if pinned_exercise is not None and len(pattern_pool) > 1:
                    stat_pool = [
                        e for e in pattern_pool if e.id != existing_pin.exercise_id
                    ] or pattern_pool

                skill_pool = [e for e in stat_pool if e.id in priority_exercise_ids] or stat_pool
                balanced_pool = self._apply_muscle_balance(skill_pool, picked)
                choice = random.choice(balanced_pool)

                if training_block is not None:
                    if existing_pin is not None:
                        existing_pin.exercise_id = choice.id
                        existing_pin.block_number = training_block.block_number
                    else:
                        self._session.add(
                            UserMovementPatternVariant(
                                user_id=user.id,
                                category=category,
                                movement_pattern=pattern,
                                exercise_id=choice.id,
                                block_number=training_block.block_number,
                            )
                        )

            picked.append(choice)
            picked_ids.add(choice.id)
        return picked

    @staticmethod
    def _apply_muscle_balance(pool: list[Exercise], picked: list[Exercise]) -> list[Exercise]:
        """Soft push/pull/legs/core variety rule: avoid a third main-block pick
        in a row from the same muscle_group, applied *within* whatever pool
        the skill-priority step above already narrowed to -- so a user's
        SkillTag priority always wins a conflict, this never reaches back
        into the wider stat pool to find variety the priority pool doesn't
        have.

        Exercises with muscle_group=None (on_ice drills, and off_ice cardio/
        mental work that isn't push/pull/legs/core) never block a streak and
        are never filtered out by one -- the rule is off_ice-anatomy-only,
        and None means "not applicable" rather than a group of its own.

        Falls back to the untouched pool whenever avoiding the streak would
        empty it, so a main slot is never left unfilled for this reason.
        """
        if len(picked) < 2:
            return pool
        last_group, previous_group = picked[-1].muscle_group, picked[-2].muscle_group
        if last_group is None or last_group != previous_group:
            return pool

        varied = [e for e in pool if e.muscle_group is None or e.muscle_group != last_group]
        return varied or pool

    @staticmethod
    def _apply_level_cap(
        candidates: list[Exercise],
        user: User,
        *,
        context: str,
        level_cap: int | None = None,
    ) -> list[Exercise]:
        """Hard difficulty ceiling from User.level (see max_difficulty_for_level),
        further lowered by the Phase 5 structural overload brake (see
        app.core.training_block.effective_difficulty_cap) -- applied at
        exercise-*assembly* time only -- never touches SessionBlocks
        already saved into a plan, even if the user's level or throttle
        later makes one of them ineligible for a fresh pick.

        Last-resort fallback: if nothing in `candidates` is under the cap
        (e.g. a low-level or currently-throttled user's catalog has no easy
        exercises for this phase/category/stat), relax back to the full,
        uncapped `candidates` rather than assembling an empty/broken plan --
        and log it, since an empty pool under the cap is a catalog gap
        worth knowing about.
        """
        level_cap = level_cap if level_cap is not None else max_difficulty_for_level(user.level)
        cap = effective_difficulty_cap(level_cap, user.difficulty_throttle_steps)
        capped = [e for e in candidates if e.difficulty_level <= cap]
        if capped:
            return capped

        logger.warning(
            "No exercises with difficulty<=%s available for %s (user_id=%s, level=%s) -- "
            "falling back to the full difficulty range so the plan isn't left empty",
            cap,
            context,
            user.id,
            user.level,
        )
        return candidates

    # -- training-party support --
    #
    # Shared by TrainingPartyService for the "everyone trains the same
    # exercises" flow: suggest_party_exercises picks a co-op-friendly set,
    # ensure_day_plan_for_date/replace_day_plan_content materialize it into
    # a *member's own* DayPlan/TrainingSession/SessionBlock rows -- there is
    # no party-specific storage, these are the exact same tables personal
    # plans use.

    async def suggest_party_exercises(self, members: list[User], count: int) -> list[Exercise]:
        """Off-ice, MAIN-phase candidates every member in `members` can both
        equip for and handle, spread across as many different
        movement_pattern values as possible (never more than one exercise
        per pattern -- same membership-based bucketing as _pick_main, see
        its docstring for why target_stat was replaced with this axis).

        On-ice is deliberately out of scope here: it isn't equipment-gated
        at all (see ExerciseRepository.list_for_assembly), so it wouldn't
        exercise the "shared equipment" requirement this exists for, and a
        co-op session is naturally an off-ice/gym-or-home affair -- nothing
        in this app coordinates multiple players actually being on the same
        ice at once.

        Equipment: deliberately NOT list_for_assembly's exact-match
        `equipment_type == equipment_access` rule -- that rule is a single
        user's constraint, and applying it per member and intersecting the
        results would mean any two members with *different* equipment_access
        share literally nothing (an exercise's equipment_type can equal at
        most one of two different values), even though someone with gym
        access can obviously still do a bodyweight-only move. Instead
        equipment_access is treated as cumulative capability via
        _EQUIPMENT_REACH (gym implies home implies bodyweight) and an
        exercise is eligible only if its equipment_type is reachable for
        *every* member -- the actual "intersection of what everyone can do".

        Difficulty: capped at min(max_difficulty_for_level(m.level) for m in
        members) -- the *weakest* member's ceiling -- and never relaxed past
        that even if a stat ends up with no eligible candidates (unlike
        _apply_level_cap's last-resort fallback for personal plans, which
        would relax the cap rather than leave a slot unfilled). Overloading
        someone is worse here than a shorter suggested list.
        """
        if not members:
            return []

        candidates = await self._exercises.list_exercises(
            category=ExerciseCategory.OFF_ICE, phase=TrainingPhase.MAIN
        )
        reachable_sets = [_EQUIPMENT_REACH[member.equipment_access] for member in members]
        eligible = [
            exercise
            for exercise in candidates
            if all(exercise.equipment_type in reach for reach in reachable_sets)
        ]

        cap = min(max_difficulty_for_level(member.level) for member in members)
        eligible = [exercise for exercise in eligible if exercise.difficulty_level <= cap]

        # Same movement_pattern membership-bucketing as _pick_main -- see the
        # comment there.
        patterns_by_exercise = await self._exercises.list_movement_patterns_by_exercise(
            [exercise.id for exercise in eligible]
        )
        by_pattern: dict[MovementPattern, list[Exercise]] = defaultdict(list)
        for exercise in eligible:
            for pattern in patterns_by_exercise.get(exercise.id, ()):
                by_pattern[pattern].append(exercise)

        picked: list[Exercise] = []
        picked_ids: set[uuid.UUID] = set()
        patterns = list(MovementPattern)
        random.shuffle(patterns)
        for pattern in patterns:
            if len(picked) >= count:
                break
            pattern_pool = [e for e in by_pattern.get(pattern, ()) if e.id not in picked_ids]
            if not pattern_pool:
                continue
            choice = random.choice(pattern_pool)
            picked.append(choice)
            picked_ids.add(choice.id)
        return picked

    async def ensure_day_plan_for_date(self, user: User, target_date: date) -> DayPlan:
        """Return the user's DayPlan for target_date, creating a brand-new
        WeeklyPlan for it from scratch if none exists yet (the
        no_plan_for_date case from TrainingPartyService's status resolution).

        The fabricated week is a full 7 days -- target_date gets a REST
        placeholder (replace_day_plan_content overwrites it right after) and
        every other day of that week is also REST -- rather than a lone
        1-day WeeklyPlan. A partial week would permanently strand the rest
        of it: create_weekly_plan requires exactly 7 days and would 409 on
        this same week later, and patch_weekly_plan can't add a day that
        isn't already part of the plan. A full (if mostly-REST) week keeps
        every existing schedule endpoint able to read and patch it normally.
        """
        day_plan = await self._schedule.get_day_plan_for_date(user.id, target_date)
        if day_plan is not None:
            return day_plan

        week_start = target_date - timedelta(days=target_date.weekday())
        training_block = await self._training_block_service.get_or_create_and_resolve(user.id)
        weekly_plan = WeeklyPlan(
            user_id=user.id, week_start_date=week_start, training_block_id=training_block.id
        )
        for offset in range(7):
            # training_session=None explicitly, not left to default -- once
            # flushed this becomes a persistent instance, and an *unset*
            # one-to-one reverse relationship on a persistent instance lazy-
            # loads on next access (there's no local way to know a related
            # TrainingSession row doesn't exist without asking the DB).
            # ensure_day_plan_for_date's caller reads .training_session on
            # this exact in-memory object right after, synchronously, which
            # a lazy load can't service outside AsyncSession's greenlet --
            # setting it explicitly marks it already-loaded instead.
            weekly_plan.day_plans.append(
                DayPlan(
                    date=week_start + timedelta(days=offset),
                    session_type=DaySessionType.REST,
                    training_session=None,
                )
            )

        await self._schedule.save(weekly_plan)
        return next(dp for dp in weekly_plan.day_plans if dp.date == target_date)

    async def replace_day_plan_content(
        self, day_plan: DayPlan, exercise_ids: list[uuid.UUID], user: User
    ) -> None:
        """Overwrite day_plan's TrainingSession with the party's finalized
        MAIN-phase exercises plus a warmup/cooldown picked for `user`
        specifically -- same pattern-matching-against-MAIN approach
        _build_training_session uses for solo sessions (Phase 3), narrowed
        to this member's own equipment/level/current block phase. Used to
        materialize a party's finalized exercise set into a member's own
        plan, replacing whatever was there (rest, a fresh REST placeholder
        from ensure_day_plan_for_date, or an untouched personal session)
        exactly once per confirm/late-join.

        A co-op session used to be MAIN-only, with no warmup/cooldown at
        all -- every member picks their own here rather than sharing one,
        since equipment/level/block phase can differ member to member even
        though the MAIN exercises are identical for everyone.

        Same explicit delete-then-flush-then-attach as _patch_weekly_plan,
        and for the same reason: TrainingSession.day_plan_id is unique and
        SQLAlchemy doesn't guarantee this flush's DELETE orders before the
        replacement's INSERT if the relationship were just reassigned.
        """
        if day_plan.training_session is not None:
            await self._session.delete(day_plan.training_session)
            await self._session.flush()
            day_plan.training_session = None

        day_plan.session_type = DaySessionType.OFF_ICE

        training_block = await self._training_block_service.get_or_create_and_resolve(user.id)
        block_phase = await self._overload_service.apply_brakes(user, training_block.phase)
        main_patterns = await self._movement_patterns_union(exercise_ids)
        warmup = await self._pick_single(
            TrainingPhase.WARMUP,
            ExerciseCategory.OFF_ICE,
            user,
            block_phase,
            preferred_patterns=main_patterns,
        )
        cooldown = await self._pick_single(
            TrainingPhase.COOLDOWN,
            ExerciseCategory.OFF_ICE,
            user,
            block_phase,
            preferred_patterns=main_patterns,
        )

        # Same running-order idiom as _build_training_session -- order runs
        # across the whole session, not reset per phase.
        blocks: list[SessionBlock] = []
        if warmup is not None:
            blocks.append(SessionBlock(phase=TrainingPhase.WARMUP, exercise_id=warmup.id, order=len(blocks)))
        for exercise_id in exercise_ids:
            blocks.append(SessionBlock(phase=TrainingPhase.MAIN, exercise_id=exercise_id, order=len(blocks)))
        if cooldown is not None:
            blocks.append(
                SessionBlock(phase=TrainingPhase.COOLDOWN, exercise_id=cooldown.id, order=len(blocks))
            )

        day_plan.training_session = TrainingSession(blocks=blocks)
        await self._session.flush()

    async def _to_read_schema(self, weekly_plan: WeeklyPlan) -> WeeklyPlanRead:
        exercise_ids = [
            block.exercise_id
            for day in weekly_plan.day_plans
            if day.training_session is not None
            for block in day.training_session.blocks
        ]
        stats_by_id = await self._exercises.list_target_stats_by_exercise(exercise_ids)

        day_reads = []
        for day in weekly_plan.day_plans:
            session_read = None
            if day.training_session is not None:
                # GAME has no ExerciseCategory of its own (see
                # _build_game_day_session) -- warmup-only by construction, so
                # its split is fixed rather than estimated from blocks that
                # are all the same phase anyway.
                block_pairs = [(block.phase, block.exercise) for block in day.training_session.blocks]
                if day.session_type == DaySessionType.GAME:
                    phase_split = {TrainingPhase.WARMUP: 1.0}
                else:
                    phase_split = compute_phase_split(block_pairs)
                duration_seconds = estimate_session_duration_seconds(block_pairs)
                blocks_read = [
                    SessionBlockRead(
                        id=block.id,
                        phase=block.phase,
                        order=block.order,
                        completed_at=block.completed_at,
                        exercise=exercise_to_read(
                            block.exercise, stats_by_id.get(block.exercise_id, [])
                        ),
                    )
                    for block in day.training_session.blocks
                ]
                session_read = TrainingSessionRead(
                    id=day.training_session.id,
                    phase_split=phase_split,
                    duration_seconds=duration_seconds,
                    blocks=blocks_read,
                )
            day_reads.append(
                DayPlanRead(
                    id=day.id,
                    date=day.date,
                    session_type=day.session_type,
                    on_ice_minutes=day.on_ice_minutes,
                    training_session=session_read,
                )
            )
        return WeeklyPlanRead(
            id=weekly_plan.id, week_start_date=weekly_plan.week_start_date, day_plans=day_reads
        )
