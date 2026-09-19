import itertools
import logging
import random
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Iterator
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.day_archetype import (
    ARCHETYPE_ELIGIBLE_PATTERNS,
    DAY_ARCHETYPES,
    PATTERN_ARCHETYPES,
    ROTATING_PATTERNS,
    ROTATION_SESSION_LIMIT,
    choose_archetype,
    forces_technical_archetype,
    initial_rotation_order,
)
from app.core.session_duration import compute_phase_split, estimate_session_duration_seconds
from app.core.stat_difficulty import UNCLASSIFIED_EXERCISE_CAP, max_difficulty_for_stat
from app.core.training_block import (
    DIFFICULTY_PRIORITY_PREDICATES,
    MAX_DIFFICULTY_LEVEL,
    effective_difficulty_cap,
    is_final_taper_week,
    is_tapering,
    main_exercise_count_range,
    max_difficulty_for_level,
)
from app.models.exercise import (
    GYM_COVERED_ITEMS,
    WARMUP_STAGE_ORDER,
    EquipmentItem,
    Exercise,
    ExerciseCategory,
    MovementPattern,
    MuscleGroup,
    StimulusType,
    TargetStat,
    TrainingPhase,
    UserMovementPatternVariant,
)
from app.models.progress import UserStat
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
from app.repositories.progress_repository import ProgressRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.repositories.skill_repository import SkillRepository
from app.repositories.training_diary_repository import TrainingDiaryRepository
from app.repositories.user_movement_pattern_variant_repository import (
    UserMovementPatternVariantRepository,
)
from app.repositories.user_skill_preference_repository import UserSkillPreferenceRepository
from app.schemas.exercise import exercise_to_read
from app.schemas.schedule import (
    CeilingEscalationRead,
    DayPlanIn,
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
from app.services.reps_suggestion_service import RepsSuggestionService
from app.services.stat_service import get_effective_value
from app.services.training_block_service import TrainingBlockService

logger = logging.getLogger(__name__)

# _build_session_for_day's real dispatch only ever reaches
# _build_training_session for OFF_ICE now (ON_ICE has its own
# _build_on_ice_day_session, no MAIN block) -- the ON_ICE entry stays here
# so _build_training_session/_pick_main remain directly callable/testable
# for either category, without needing a narrower, ON_ICE-less dict.
_SESSION_TYPE_TO_CATEGORY = {
    DaySessionType.ON_ICE: ExerciseCategory.ON_ICE,
    DaySessionType.OFF_ICE: ExerciseCategory.OFF_ICE,
}

# _pick_main's four role pattern-sets, pulled out to module level so
# replace_block_exercise (Stage 1.5, 2026-08-20 planning session -- manual
# single-slot swap, "тренажёр занят") can determine "which role is this MAIN
# exercise in" without duplicating the literal pattern lists a second time.
# Role 4 (accessories) has no fixed set of its own -- it's everything these
# three don't claim, computed by _role_patterns_for below.
_EXPLOSIVE_PATTERNS: tuple[MovementPattern, ...] = (
    MovementPattern.LOCOMOTION, MovementPattern.STICK_HANDLING, MovementPattern.COORDINATION,
)
_LOWER_BODY_PATTERNS: tuple[MovementPattern, ...] = (MovementPattern.SQUAT, MovementPattern.HIP_HINGE)
_UPPER_BODY_PATTERNS: tuple[MovementPattern, ...] = (MovementPattern.PUSH, MovementPattern.PULL)

# 2026-09-19 audit round 3 item #4: ROTATING_PATTERNS' own same-variant
# session cap (see its docstring) was deliberately scoped to the 7
# patterns *without* a 3-archetype split -- squat/hip_hinge/push/pull
# were left out because ARCHETYPE_ELIGIBLE_PATTERNS already splits them
# by load type (strength/power/skill). But that split is across
# *different* stimulus lines, not variety *within* one -- a squat/POWER
# pin still holds the exact same variant for the whole training block
# (8+ weeks), same "same exercise for weeks" complaint ROTATING_PATTERNS
# already fixed for everything else. Confirmed against the real catalog:
# 39 squat/power candidates, zero content shortage, yet a user reported
# the exact same one-legged jump for two months straight. Combining the
# two sets here (rather than editing ROTATING_PATTERNS itself, which
# stays "the non-archetype-eligible ones" per its own docstring) lets
# both call sites below share one check. Per-archetype-line granularity
# comes for free: existing_pins/row are already keyed on (pattern,
# archetype), so squat/STRENGTH, squat/POWER and squat/SKILL each carry
# their own independent times_chosen counter and rotate independently.
_SESSION_CAP_ROTATED_PATTERNS: frozenset[MovementPattern] = ROTATING_PATTERNS | ARCHETYPE_ELIGIBLE_PATTERNS


# Final coherence validator (Stage 2.4, 2026-08-20 planning session):
# "не более N упражнений на одну мышцу" -- see _pick_main's own call site
# and ScheduleService._enforce_muscle_group_cap for what happens when a
# session exceeds this after all 4 roles are filled. 3 allows the normal,
# expected case of two or three MAIN exercises sharing a muscle group in
# passing (e.g. a squat and a lunge both loading QUADS) without flagging
# it -- a 4th independent hit is what the plan calls a real pile-up.
MAX_EXERCISES_PER_MUSCLE_GROUP = 3


def _role_patterns_for(patterns: set[MovementPattern]) -> frozenset[MovementPattern]:
    """Which of _pick_main's four roles `patterns` (a replaced exercise's own
    tags) belongs to, as that role's full pattern set -- e.g. a HIP_HINGE
    exercise maps to {SQUAT, HIP_HINGE} (role 2 as a whole), not just
    {HIP_HINGE}, so a squat is an acceptable substitute for a hip hinge and
    vice versa, same as _pick_main treats that role's slot. Falls through to
    role 4 (every pattern not claimed by roles 1-3) for anything else,
    including a completely untagged exercise (empty `patterns`)."""
    if patterns & set(_EXPLOSIVE_PATTERNS):
        return frozenset(_EXPLOSIVE_PATTERNS)
    if patterns & set(_LOWER_BODY_PATTERNS):
        return frozenset(_LOWER_BODY_PATTERNS)
    if patterns & set(_UPPER_BODY_PATTERNS):
        return frozenset(_UPPER_BODY_PATTERNS)
    return frozenset(MovementPattern) - frozenset(_EXPLOSIVE_PATTERNS) - frozenset(
        _LOWER_BODY_PATTERNS
    ) - frozenset(_UPPER_BODY_PATTERNS)

# Warmup/cooldown as a short sequence instead of one exercise (product ask:
# "always a proper warmup complex" + "cooldown should stretch what MAIN just
# worked", 2026-08-18). Warmup picks one exercise per WarmupStage, in
# WARMUP_STAGE_ORDER (soft tissue -> raise -> joint mobility -> activation
# -> dynamic) -- see _pick_warmup_complex -- general readiness structured
# like a real warmup, not muscle-specific. Cooldown is instead sized to how
# many distinct movement_patterns MAIN actually hit (capped at
# _COOLDOWN_SEQUENCE_MAX so a big accumulation-phase MAIN block doesn't blow
# cooldown out to 6 stretches), so a session with 3 MAIN patterns gets 3
# cooldown picks each preferring to match one of them, rather than 1 pick
# that only happens to overlap one of them.
_COOLDOWN_SEQUENCE_MAX = 4

# P3 item #8: optional 10-15min puck-handling tail-on to a normal OFF_ICE
# session, gated on owning a hockey stick -- see
# ScheduleService._pick_puck_module_exercises. Rough duration budget at
# the existing per-exercise estimates; non-binding today since the real
# catalog only has 3 STICK_HANDLING-pattern exercises total.
_PUCK_MODULE_MAX_EXERCISES = 4

# 2026-09-18 audit round 2 item #4: _choose_guaranteed_slot_dates' own RNG,
# deliberately separate from the module-level random.choice/shuffle every
# other picker in this file uses -- see that method's own docstring for why.
_GUARANTEED_SLOT_RNG = random.Random()


class ScheduleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._exercises = ExerciseRepository(session)
        self._progress = ProgressRepository(session)
        self._schedule = ScheduleRepository(session)
        self._skills = SkillRepository(session)
        self._user_skill_preferences = UserSkillPreferenceRepository(session)
        self._variants = UserMovementPatternVariantRepository(session)
        self._training_block_service = TrainingBlockService(session)
        self._overload_service = OverloadService(session)
        self._reps_suggestions = RepsSuggestionService(session)
        self._diary = TrainingDiaryRepository(session)

    @staticmethod
    def _choose_guaranteed_slot_dates(days: list[DayPlanIn]) -> tuple[date | None, date | None]:
        """2026-09-18 audit round 2 item #4 ("выносливость и катание почти не
        попадают в основной блок"): which OFF_ICE day, if any, gets this
        batch's guaranteed endurance-stimulus accessory pick, and which gets
        its guaranteed locomotion ("катание") pick -- see _pick_main's
        guarantee_endurance/guarantee_locomotion params. Chosen ONCE per
        batch (a single create_weekly_plan/_patch_weekly_plan call), the
        same scoping _build_archetype_rotation already uses and for the
        same reason: there's no separate persisted "this week's guarantee
        is already satisfied" record, so a later, separate patch call to
        different days of the same week can independently choose its own
        guarantee day again. Accepted, same as archetype_rotation's own
        scoping.

        Endurance and locomotion dates are chosen independently (may land
        on the same day or different days) -- _pick_main's own role-4 logic
        folds them onto a single accessory slot when they do and the
        catalog allows it. None for an axis (or both) when `days` has no
        OFF_ICE entry at all -- no day to guarantee anything into, same
        "never force a slot that can't exist" convention as every other
        best-effort layer in this file.

        Uses its own random.Random() instance rather than the module-level
        random.choice every other picker in this file goes through --
        several test files (test_puck_module.py, test_schedule_service_
        game_day.py, ...) monkeypatch random.choice/shuffle process-wide
        assuming every call is choosing between Exercise-like objects
        (`sorted(pool, key=lambda e: e.name)`), which breaks on a plain
        `date`. A dedicated instance sidesteps that without touching those
        tests' own conventions -- this is the only picker in the class
        choosing between dates, not exercises, so it doesn't need the
        same test-wide determinism hook the others share.
        """
        off_ice_dates = [d.date for d in days if d.session_type == DaySessionType.OFF_ICE]
        if not off_ice_dates:
            return None, None
        return _GUARANTEED_SLOT_RNG.choice(off_ice_dates), _GUARANTEED_SLOT_RNG.choice(off_ice_dates)

    async def create_weekly_plan(self, user: User, payload: WeeklyPlanCreate) -> WeeklyPlanRead:
        dates = [day.date for day in payload.days]
        if len(set(dates)) != len(dates):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate dates in weekly plan"
            )

        target_week_start_date = min(dates)
        training_block = await self._training_block_service.get_or_create_and_resolve(user.id)
        block_phase = await self._overload_service.apply_brakes(user, training_block.phase)
        archetype_rotation = await self._build_archetype_rotation(user, ExerciseCategory.OFF_ICE)
        endurance_date, locomotion_date = self._choose_guaranteed_slot_dates(payload.days)

        weekly_plan = WeeklyPlan(
            user_id=user.id, week_start_date=target_week_start_date, training_block_id=training_block.id
        )
        for day_in in payload.days:
            day_plan = DayPlan(
                date=day_in.date,
                session_type=day_in.session_type,
            )
            if day_in.session_type != DaySessionType.REST:
                day_plan.training_session = await self._build_session_for_day(
                    day_in.session_type,
                    user,
                    block_phase,
                    training_block,
                    today=day_in.date,
                    archetype_rotation=archetype_rotation,
                    guarantee_endurance=day_in.date == endurance_date,
                    guarantee_locomotion=day_in.date == locomotion_date,
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
        # 2026-09-18 fix (audit round 2 item #3, continuation of round 1
        # item #10): date.today() read the *server's* timezone -- see
        # ProgressService.get_streak's matching fix for the full reasoning.
        today = datetime.now(ZoneInfo(user.timezone)).date()
        weekly_plan = await self._schedule.get_current(user.id, today)
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
            # 2026-09-18 fix (audit round 2 item #3): see
            # get_current_weekly_plan's matching fix above.
            today = datetime.now(ZoneInfo(user.timezone)).date()
            weekly_plan = await self._schedule.get_current(user.id, today)
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
        archetype_rotation = await self._build_archetype_rotation(user, ExerciseCategory.OFF_ICE)
        endurance_date, locomotion_date = self._choose_guaranteed_slot_dates(payload.days)

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
                    day_in.session_type,
                    user,
                    block_phase,
                    training_block,
                    today=day_in.date,
                    archetype_rotation=archetype_rotation,
                    guarantee_endurance=day_in.date == endurance_date,
                    guarantee_locomotion=day_in.date == locomotion_date,
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
        archetype_rotation: dict[MovementPattern, Iterator[StimulusType]] | None = None,
        guarantee_endurance: bool = False,
        guarantee_locomotion: bool = False,
    ) -> TrainingSession:
        """Dispatch to the GAME-day builder (light activation only), the
        ON_ICE-day builder (on-ice warmup+cooldown only, no MAIN -- see
        _build_on_ice_day_session), or the regular OFF_ICE builder -- the
        single place both create_weekly_plan and _patch_weekly_plan go
        through, so neither has to know GAME/ON_ICE are special cases.

        training_block (Phase: П.3), today (Phase: П.5, tournament taper),
        archetype_rotation (batch-wide round-robin, see
        _build_archetype_rotation) and guarantee_endurance/
        guarantee_locomotion (round 2 audit item #4, see
        _choose_guaranteed_slot_dates) are only ever consumed by the
        regular builder's _pick_main -- GAME/ON_ICE days have no MAIN
        block at all, so neither of their builders needs any of them.
        """
        if session_type == DaySessionType.GAME:
            return await self._build_game_day_session(user, block_phase)
        if session_type == DaySessionType.ON_ICE:
            return await self._build_on_ice_day_session(user, block_phase)
        return await self._build_training_session(
            session_type, user, block_phase, training_block, today=today,
            archetype_rotation=archetype_rotation,
            guarantee_endurance=guarantee_endurance,
            guarantee_locomotion=guarantee_locomotion,
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
            phase=TrainingPhase.WARMUP, user=user
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

        candidates, _ = await self._apply_difficulty_gate(candidates, user, context="game/mental_prep")
        return random.choice(candidates)

    async def _build_on_ice_day_session(
        self, user: User, block_phase: BlockPhase
    ) -> TrainingSession:
        """ON_ICE day: on-ice warmup + cooldown wrapped around a coach-run
        team practice the app has no content for -- no MAIN block. Unlike
        GAME (location-ambiguous, single light activation pick), this is
        definitely an on-ice day, so it gets the same full RAMP-protocol
        warmup complex a normal on-ice session would. No preferred_patterns/
        preferred_muscle_groups passed to either pick -- there's no MAIN to
        match against, so both layers fall back to their unmatched pool
        (same "skips this layer entirely" behavior already documented on
        _pick_single/_pick_warmup_complex for the empty case).
        """
        warmup_exercises = await self._pick_warmup_complex(ExerciseCategory.ON_ICE, user, block_phase)
        cooldown_exercises = await self._pick_sequence(
            TrainingPhase.COOLDOWN, ExerciseCategory.ON_ICE, user, block_phase, count=_COOLDOWN_SEQUENCE_MAX
        )

        blocks: list[SessionBlock] = []
        for exercise in warmup_exercises:
            blocks.append(SessionBlock(phase=TrainingPhase.WARMUP, exercise_id=exercise.id, order=len(blocks)))
        for exercise in cooldown_exercises:
            blocks.append(SessionBlock(phase=TrainingPhase.COOLDOWN, exercise_id=exercise.id, order=len(blocks)))

        return TrainingSession(blocks=blocks)

    async def _build_training_session(
        self,
        session_type: DaySessionType,
        user: User,
        block_phase: BlockPhase,
        training_block: TrainingBlock | None = None,
        *,
        today: date | None = None,
        archetype_rotation: dict[MovementPattern, Iterator[StimulusType]] | None = None,
        guarantee_endurance: bool = False,
        guarantee_locomotion: bool = False,
    ) -> TrainingSession:
        """MAIN is picked first and warmup/cooldown are chosen retrospectively
        to match it (Phase 3) -- storage order of `blocks` is still
        warmup/main/cooldown, only the *decision* order changed, so this
        picks main before appending anything, then builds `blocks` in the
        original display order once every pick is known.
        """
        category = _SESSION_TYPE_TO_CATEGORY[session_type]

        main_exercises = await self._pick_main(
            category,
            user,
            block_phase,
            training_block=training_block,
            today=today,
            archetype_rotation=archetype_rotation,
            guarantee_endurance=guarantee_endurance,
            guarantee_locomotion=guarantee_locomotion,
        )
        main_exercise_ids = [exercise.id for exercise in main_exercises]
        main_patterns = await self._movement_patterns_union(main_exercise_ids)
        main_muscle_groups = await self._muscle_groups_union(main_exercise_ids)

        warmup_exercises = await self._pick_warmup_complex(
            category,
            user,
            block_phase,
            preferred_patterns=main_patterns,
            preferred_muscle_groups=main_muscle_groups,
        )
        # One cooldown pick per distinct pattern MAIN actually trained
        # (capped) -- see _COOLDOWN_SEQUENCE_MAX's own comment. main_patterns
        # empty (MAIN itself came back empty) still asks for
        # _COOLDOWN_SEQUENCE_MAX so a broken/empty MAIN doesn't also zero
        # out cooldown.
        cooldown_count = min(_COOLDOWN_SEQUENCE_MAX, len(main_patterns)) or _COOLDOWN_SEQUENCE_MAX
        cooldown_exercises = await self._pick_sequence(
            TrainingPhase.COOLDOWN,
            category,
            user,
            block_phase,
            count=cooldown_count,
            preferred_patterns=main_patterns,
            preferred_muscle_groups=main_muscle_groups,
        )

        # P3 item #8: optional puck-handling tail-on, gated on owning a
        # hockey stick -- see _pick_puck_module_exercises. Only reachable
        # here for OFF_ICE (this method's only real caller,
        # _build_session_for_day, never routes ON_ICE through it).
        puck_module_exercises = await self._pick_puck_module_exercises(user, block_phase)

        # order runs across the whole session, not reset per phase (same
        # len(blocks) idiom _build_game_day_session already uses below) --
        # resetting it per phase left every session with warmup/main[0]/
        # cooldown all sharing order=0, which made TrainingSession.blocks'
        # order_by="SessionBlock.order" (a single global sort) fall back to
        # whatever tiebreak order the DB happened to return them in instead
        # of the intended warmup-then-main-then-cooldown sequence.
        blocks: list[SessionBlock] = []
        for exercise in warmup_exercises:
            blocks.append(SessionBlock(phase=TrainingPhase.WARMUP, exercise_id=exercise.id, order=len(blocks)))

        for exercise in main_exercises:
            blocks.append(SessionBlock(phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=len(blocks)))

        for exercise in cooldown_exercises:
            blocks.append(SessionBlock(phase=TrainingPhase.COOLDOWN, exercise_id=exercise.id, order=len(blocks)))

        # Own TrainingPhase.PUCK, appended last -- a visually separate
        # "Владение шайбой" section in the UI (frontend renders it after
        # Заминка, matching this same tail-on ordering), not folded into
        # "Основная часть".
        for exercise in puck_module_exercises:
            blocks.append(SessionBlock(phase=TrainingPhase.PUCK, exercise_id=exercise.id, order=len(blocks)))

        return TrainingSession(blocks=blocks)

    async def _pick_puck_module_exercises(
        self, user: User, block_phase: BlockPhase
    ) -> list[Exercise]:
        """P3 item #8: optional 10-15min puck-handling tail-on to a normal
        OFF_ICE session, gated on "stick present in inventory today" --
        same personal-gear ownership check the hockey-stick bug fix (P1#1)
        introduced, kept explicit here rather than relying only on the
        per-exercise equipment filter already inside list_for_assembly
        (belt-and-suspenders: a future TrainingPhase.PUCK exercise added
        without its own ExerciseEquipmentItem(HOCKEY_STICK) row would
        otherwise silently leak to non-owners -- the exact "filter looked
        complete but wasn't" shape that bug already was).

        Candidates come from TrainingPhase.PUCK specifically, not a
        MovementPattern.STICK_HANDLING filter over TrainingPhase.MAIN --
        the phase itself is now the authoritative "this is puck-module
        content" tag (see scripts/seed_exercises.py's _PHASE_OVERRIDES),
        so no overlap with the regular MAIN pool is possible by
        construction; nothing to exclude_ids against.
        """
        owned = await self._exercises.list_owned_equipment(user.id)
        if EquipmentItem.HOCKEY_STICK not in owned:
            return []

        pool = await self._exercises.list_for_assembly(
            phase=TrainingPhase.PUCK, user=user, category=ExerciseCategory.OFF_ICE
        )
        if not pool:
            return []

        pool, _ = await self._apply_difficulty_gate(pool, user, context="off_ice/puck_module")
        random.shuffle(pool)
        return pool[:_PUCK_MODULE_MAX_EXERCISES]

    async def _movement_patterns_union(self, exercise_ids: list[uuid.UUID]) -> set[MovementPattern]:
        by_exercise = await self._exercises.list_movement_patterns_by_exercise(exercise_ids)
        return {pattern for patterns in by_exercise.values() for pattern in patterns}

    async def _muscle_groups_union(self, exercise_ids: list[uuid.UUID]) -> set[MuscleGroup]:
        """Stage 2.5: same shape as _movement_patterns_union -- every muscle
        group MAIN's picks load between them, the primary "what should
        warmup/cooldown target" signal for _pick_warmup_complex/
        _pick_sequence (see their own docstrings for the fallback chain to
        preferred_patterns)."""
        by_exercise = await self._exercises.list_muscle_groups_by_exercise(exercise_ids)
        return {group for groups in by_exercise.values() for group in groups}

    async def _pick_single(
        self,
        phase: TrainingPhase,
        category: ExerciseCategory,
        user: User,
        block_phase: BlockPhase,
        *,
        suitable_for_game_day: bool | None = None,
        preferred_patterns: set[MovementPattern] | None = None,
        exclude_ids: set[uuid.UUID] | None = None,
    ) -> Exercise | None:
        """Warmup/cooldown: curated pool for the phase, filtered by the day's category.

        exclude_ids (Stage 1.5, 2026-08-20 planning session: manual
        single-slot replacement) drops specific exercise ids from the pool
        before anything else runs -- unset for every fresh-assembly caller,
        only replace_block_exercise passes it, to keep the outgoing
        exercise and every other exercise already in today's session out of
        the substitute pool.

        Equipment (Stage 2.2: has_gym_access + owned items) still narrows
        off_ice candidates but never excludes on_ice ones (no equipment
        choice on the ice). The readiness gate
        caps which difficulty tier is even eligible (see
        _apply_difficulty_gate -- off-ice: UserStat, on-ice: User.level),
        and *then* the active block's phase biases difficulty within
        whatever that cap allows (intensification prefers difficulty>=4,
        deload prefers difficulty<=2), falling back to the capped pool when nothing
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
            user=user,
            category=category,
            suitable_for_game_day=suitable_for_game_day,
        )
        if exclude_ids:
            candidates = [e for e in candidates if e.id not in exclude_ids]
        if not candidates:
            return None

        candidates, gate_exhausted = await self._apply_difficulty_gate(
            candidates, user, context=f"{phase}/{category}"
        )

        difficulty_predicate = DIFFICULTY_PRIORITY_PREDICATES.get(block_phase)
        # 2026-09-17 fix (audit item #2): never apply a phase's "prefer the
        # heaviest"/"prefer the lightest" bias on top of an already-
        # exhausted readiness gate -- see _apply_difficulty_gate's
        # docstring.
        if difficulty_predicate is not None and not gate_exhausted:
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

    async def _pick_sequence(
        self,
        phase: TrainingPhase,
        category: ExerciseCategory,
        user: User,
        block_phase: BlockPhase,
        *,
        count: int,
        preferred_patterns: set[MovementPattern] | None = None,
        preferred_muscle_groups: set[MuscleGroup] | None = None,
    ) -> list[Exercise]:
        """Same candidate gathering/level-cap/difficulty-predicate layers as
        _pick_single, but returns up to `count` distinct exercises instead of
        one -- the warmup-complex/muscle-matched-cooldown feature.

        Stage 2.5 (2026-08-20 planning session): the "what should this
        target" signal is muscle groups actually loaded by MAIN
        (preferred_muscle_groups), not movement_pattern overlap -- more
        honest for "stretch what MAIN just worked" than "shares a squat/
        hip_hinge/etc label" ever was. preferred_patterns is kept as a
        fallback, not dropped: checked against the real catalog before
        writing this, zero exercises have any ExerciseMuscleGroup row yet
        (Stage 2.1 shipped the taxonomy tonight, retagging is Stage 4's
        job) -- muscle-matching alone would silently never match anything
        today. So the real order is: muscle-group intersection first: if
        that finds nothing (either no ExerciseMuscleGroup data yet, or
        this session's MAIN genuinely doesn't overlap this pool),
        movement_pattern intersection next; if that's also empty, every
        exercise in the level/difficulty-narrowed pool is equally
        eligible. Whichever tier finds a non-empty "matched" set fills the
        sequence first (shuffled among themselves), the rest of the pool
        fills any remaining slots (also shuffled) -- so a small pool never
        leaves a slot unfilled just because fewer than `count` candidates
        happen to match. Returns fewer than `count` (down to zero) if the
        pool itself is smaller than that -- never repeats an exercise to
        pad the count.
        """
        candidates = await self._exercises.list_for_assembly(
            phase=phase, user=user, category=category
        )
        if not candidates:
            return []

        candidates, gate_exhausted = await self._apply_difficulty_gate(
            candidates, user, context=f"{phase}/{category}/sequence"
        )

        difficulty_predicate = DIFFICULTY_PRIORITY_PREDICATES.get(block_phase)
        if difficulty_predicate is not None and not gate_exhausted:
            candidates = [e for e in candidates if difficulty_predicate(e)] or candidates

        matched: list[Exercise] = []
        if preferred_muscle_groups:
            muscle_groups_by_id = await self._exercises.list_muscle_groups_by_exercise(
                [e.id for e in candidates]
            )
            matched = [
                e
                for e in candidates
                if preferred_muscle_groups.intersection(muscle_groups_by_id.get(e.id, set()))
            ]
        if not matched and preferred_patterns:
            patterns_by_id = await self._exercises.list_movement_patterns_by_exercise(
                [e.id for e in candidates]
            )
            matched = [
                e
                for e in candidates
                if preferred_patterns.intersection(patterns_by_id.get(e.id, ()))
            ]

        matched_ids = {e.id for e in matched}
        rest = [e for e in candidates if e.id not in matched_ids]

        random.shuffle(matched)
        random.shuffle(rest)

        picked: list[Exercise] = []
        for exercise in matched + rest:
            if len(picked) >= count:
                break
            picked.append(exercise)
        return picked

    async def _pick_warmup_complex(
        self,
        category: ExerciseCategory,
        user: User,
        block_phase: BlockPhase,
        *,
        preferred_patterns: set[MovementPattern] | None = None,
        preferred_muscle_groups: set[MuscleGroup] | None = None,
    ) -> list[Exercise]:
        """A proper warmup: up to one exercise per WarmupStage, in
        WARMUP_STAGE_ORDER (soft tissue prep -> raise pulse/temperature ->
        joint mobility -> muscle activation -> sport-specific dynamic
        movement) -- not a flat pool pick, so a session can't end up with
        three joint-mobility drills and nothing raising the pulse.

        A stage with no candidate in the level/difficulty-narrowed,
        equipment-reachable pool (in practice: SOFT_TISSUE for a
        bodyweight-only user -- foam roller/ball work has no zero-equipment
        substitute in the catalog) is skipped outright rather than padded
        with something from a different stage -- a shorter, honest complex
        beats a technically-full one that lies about what stage it's in.

        preferred_muscle_groups (Stage 2.5, 2026-08-20 planning session)
        narrows each stage's own pool first, same fallback-to-untouched
        shape _pick_sequence uses -- see that method's docstring for why
        this, not preferred_patterns, is the primary signal now, and why
        preferred_patterns still runs as the next fallback rather than
        being dropped (zero real ExerciseMuscleGroup data yet, checked
        against the catalog before writing this).

        Exercises with warmup_stage=None (not yet classified -- see
        scripts/backfill_warmup_stages.py) are invisible to every stage
        bucket here and never get picked; that's a deliberate consequence
        of this being stage-gated, not a bug -- an unclassified WARMUP
        exercise simply isn't part of the complex until someone tags it.
        """
        candidates = await self._exercises.list_for_assembly(
            phase=TrainingPhase.WARMUP, user=user, category=category
        )
        if not candidates:
            return []

        candidates, gate_exhausted = await self._apply_difficulty_gate(
            candidates, user, context=f"warmup/{category}/complex"
        )

        difficulty_predicate = DIFFICULTY_PRIORITY_PREDICATES.get(block_phase)
        if difficulty_predicate is not None and not gate_exhausted:
            candidates = [e for e in candidates if difficulty_predicate(e)] or candidates

        muscle_groups_by_id: dict[uuid.UUID, set[MuscleGroup]] = {}
        if preferred_muscle_groups:
            muscle_groups_by_id = await self._exercises.list_muscle_groups_by_exercise(
                [e.id for e in candidates]
            )
        patterns_by_id: dict[uuid.UUID, tuple[MovementPattern, ...]] = {}
        if preferred_patterns:
            patterns_by_id = await self._exercises.list_movement_patterns_by_exercise(
                [e.id for e in candidates]
            )

        picked: list[Exercise] = []
        picked_ids: set[uuid.UUID] = set()
        for stage in WARMUP_STAGE_ORDER:
            stage_pool = [
                e for e in candidates if e.warmup_stage == stage and e.id not in picked_ids
            ]
            if not stage_pool:
                continue

            pool = []
            if preferred_muscle_groups:
                pool = [
                    e
                    for e in stage_pool
                    if preferred_muscle_groups.intersection(muscle_groups_by_id.get(e.id, set()))
                ]
            if not pool and preferred_patterns:
                pool = [
                    e
                    for e in stage_pool
                    if preferred_patterns.intersection(patterns_by_id.get(e.id, ()))
                ]
            pool = pool or stage_pool

            choice = random.choice(pool)
            picked.append(choice)
            picked_ids.add(choice.id)

        return picked

    async def _build_archetype_rotation(
        self, user: User, category: ExerciseCategory
    ) -> dict[MovementPattern, Iterator[StimulusType]]:
        """Computed ONCE per batch (a whole week, always built in one
        create_weekly_plan/_patch_weekly_plan call), before that batch's
        day-by-day loop starts -- one round-robin cycle per
        ARCHETYPE_ELIGIBLE_PATTERNS pattern, ordered by real staleness as
        of right now (see initial_rotation_order), then just cycled for
        every day _pick_main is asked to build in this same batch.

        Deliberately NOT recomputed per day: re-deriving choose_archetype
        fresh against live last_chosen_at after each day lets whichever
        archetype wins day 1 keep winning several days in a row, since it
        only advances one calendar day at a time while the untouched
        runners-up sit still (see initial_rotation_order's docstring) --
        a real, user-visible monopoly within a single generated week.
        """
        existing_pins = await self._variants.list_for_user_category(user.id, category)
        rotation: dict[MovementPattern, Iterator[StimulusType]] = {}
        for pattern in ARCHETYPE_ELIGIBLE_PATTERNS:
            pattern_candidates = PATTERN_ARCHETYPES[pattern]
            last_chosen_at = {
                candidate: existing_pins[(pattern, candidate)].last_chosen_at
                for candidate in pattern_candidates
                if (pattern, candidate) in existing_pins
            }
            rotation[pattern] = itertools.cycle(
                initial_rotation_order(last_chosen_at, pattern_candidates)
            )
        return rotation

    async def _pick_main(
        self,
        category: ExerciseCategory,
        user: User,
        block_phase: BlockPhase,
        *,
        training_block: TrainingBlock | None = None,
        today: date | None = None,
        archetype_rotation: dict[MovementPattern, Iterator[StimulusType]] | None = None,
        guarantee_endurance: bool = False,
        guarantee_locomotion: bool = False,
    ) -> list[Exercise]:
        """Stage 2.4 (2026-08-20 planning session): role-based assembly,
        replacing the old flat "shuffle every movement_pattern, fill up to
        count" loop. Up to 5-6 exercises in accumulation, 4-5 in
        intensification, 3-4 on a deload week (see
        MAIN_EXERCISE_COUNT_RANGE), at most one per movement_pattern (same
        invariant as before -- an exercise tagged with more than one
        pattern is excluded from every bucket once picked, not just the
        one that picked it), filled through four roles in FIXED order --
        this is the whole point of the rewrite, replacing "diverse but
        incoherent" with a session that actually reads as one workout:

          1. Explosive/skill, while fresh -- at most one pick, drawn from
             LOCOMOTION/STICK_HANDLING/COORDINATION (the patterns that are
             inherently power/agility/skill in character), softly
             preferring stimulus_type POWER/SKILL within whichever pattern
             has candidates. NOT archetype-dependent -- that system is
             specific to roles 2-3 below. NSCA-standard ordering: fatigue-
             sensitive neuromuscular work goes first, not proven by this
             conversation, standard S&C practice.
          2. Strength, lower body -- SQUAT and HIP_HINGE, each
             independently resolving its own "day archetype" (see below).
          3. Strength, upper body -- PUSH and PULL, same archetype
             machinery as role 2.
          4. Accessories/core -- every remaining pattern, filling up to
             `count`, aware of every muscle group already loaded by roles
             1-3 (and its own picks so far) -- see _apply_muscle_balance.

        Role 5 ("conditioning") from the planning doc is deliberately
        folded into role 4 rather than built as its own step -- the doc
        itself marks it optional and gives it none of roles 1-4's
        procedural detail; an endurance-stimulus exercise is just another
        accessory-role candidate here. Likewise there's no separate global
        "coherence validator" pass with point-fixes -- role ordering
        already guarantees explosive-first, role 2/3 picking one SQUAT/
        HIP_HINGE and one PUSH/PULL each is already a natural push/pull
        balance, and role 4's muscle-awareness already prevents pile-ups
        by construction -- a deliberate simplification, not an oversight.

        Day archetypes (roles 2-3 only): squat/hip_hinge/push/pull each
        carry three independent progression lines -- StimulusType.STRENGTH/
        POWER/SKILL, reused rather than a parallel enum (see
        app.core.day_archetype) -- instead of one pinned variant. Which
        archetype trains today is resolved per pattern by
        day_archetype.choose_archetype: whichever of the three hasn't
        trained in the longest time (an archetype with no history at all
        outranks any with a real date), defaulting to STRENGTH outright
        the very first time a pattern is ever picked for this user
        (resolved decision, not an arbitrary tie-break). day_archetype.
        forces_technical_archetype overrides this to SKILL outright,
        rotation-history untouched, whenever this session's own MAIN
        volume has already collapsed to deload's range -- a real deload
        phase, a tactical-brake-forced one (OverloadService.apply_brakes
        already forces block_phase to DELOAD before this method ever sees
        it), the final taper week, or playoffs.

        Once an archetype is resolved for a pattern, the exact same
        readiness-cap -> phase-preference -> SkillTag-priority chain runs
        as before, with one new layer inserted between phase-preference
        and SkillTag: narrow to that archetype's stimulus_type, falling
        back to the phase-narrowed pool if nothing matches (e.g. the
        catalog has zero SKILL-tagged squats right now -- checked against
        the real catalog before writing this). That insertion point is
        the resolved decision on ordering: archetype rotation wins over a
        user's SkillTag priority for these four patterns, never the other
        way around -- SkillTag priority still fully applies to every other
        pattern (role 1 and role 4) exactly as before.

        A resolved archetype's pin (UserMovementPatternVariant, now keyed
        by (pattern, archetype) instead of just pattern -- see that
        model's own docstring) works exactly like Phase П.3 always has:
        reused as-is within the same TrainingBlock, rotated to a fresh
        candidate at a real block boundary, held through a macrocycle-
        deload boundary. On top of that, Stage 2.4 also stamps
        last_chosen_at with `today` whenever the exercise actually landed
        (pin-reuse or fresh pick alike) genuinely matches the target
        archetype's stimulus_type -- a fallback pick that missed doesn't
        get to claim the archetype as "done", so an under-classified
        archetype honestly keeps getting tried instead of silently going
        quiet. training_block=None (e.g. patching a week whose block
        record is missing) skips all pin/rotation bookkeeping entirely,
        same as before this feature existed -- archetype selection still
        runs, just always sees empty history and defaults to STRENGTH.

        Bodyweight escalation (Stage 2.6, all four roles, not just
        archetype-eligible ones): a same-block pin for a tracks_weight=false
        exercise is broken early -- not waiting for the next block boundary
        -- once RepsSuggestionService.is_stuck_at_ceiling says the user has
        hit the top of its rep range with good feedback, since ordinary
        double progression has no weight lever to reach for there. The
        fresh pick that follows prefers a same-pattern candidate with a
        strictly higher difficulty_level than the outgoing one; at a real
        difficulty ceiling for that pattern (2026-09-18 audit round 2 item
        #1), a different same-difficulty variant instead of a downgrade --
        see _tier_by_escalated_difficulty. Never fires through a
        macrocycle-deload hold.

        Guaranteed endurance/locomotion slot (role 4 only, 2026-09-18 audit
        round 2 item #4): "выносливость и катание почти не попадают в
        основной блок" -- role 4's own random accessory pick almost never
        happened to land on a StimulusType.ENDURANCE exercise or the
        LOCOMOTION pattern, since neither role 1 (prefers POWER/SKILL) nor
        role 4 (no stimulus preference at all before this) favored them.
        guarantee_endurance/guarantee_locomotion, resolved once per batch
        by _choose_guaranteed_slot_dates, move whichever accessory
        pattern(s) can satisfy each into role 4's iteration order first --
        substituting a slot that would have gone to some other accessory
        pick, not adding a new one. Same softness as every other
        preference layer here: if the catalog has no ENDURANCE-stimulus
        candidate among this session's remaining accessory patterns, or
        LOCOMOTION was already claimed by role 1, the guarantee just
        doesn't fire rather than forcing an empty/wrong pick. When
        LOCOMOTION is itself the (or an) ENDURANCE-stimulus carrier, both
        guarantees fold onto its single slot instead of spending two.
        Exercises actually placed by either guarantee are protected from
        _enforce_muscle_group_cap's substitution below, so a muscle-group
        pile-up can't silently undo the one thing this feature exists to
        guarantee.

        Unilateral preference (role 2 only, hip_hinge/squat): skating is
        an inherently one-legged push, so a squat/hip_hinge exercise
        tagged Exercise.is_unilateral=True is softly preferred over a
        bilateral one within whatever pool survives every earlier layer --
        a tie-break, not a filter, since most of the catalog isn't
        classified on this axis yet.

        The count range itself can be tightened before any of this runs
        (Phase: П.4 seasonal mode) -- during the user's chosen SEASON/
        PLAYOFFS period, off-ice volume is capped lower even in
        accumulation, see app.core.training_block.main_exercise_count_range,
        which day_archetype.forces_technical_archetype also reads (see
        above). A user-set tournament_date (Phase: П.5 taper) overrides
        season_period outright on that same axis for the final
        TAPER_WINDOW_WEEKS before it. today defaults to the user's own
        today (ZoneInfo(user.timezone) -- 2026-09-18 fix, audit round 2
        item #3) for every real caller, injectable purely for
        deterministic tests/simulation, same shape as
        TrainingBlockService.resolve_active_block's own `today` param.
        """
        candidates = await self._exercises.list_for_assembly(
            phase=TrainingPhase.MAIN, user=user, category=category
        )
        if not candidates:
            return []

        resolved_today = today or datetime.now(ZoneInfo(user.timezone)).date()
        tapering = is_tapering(resolved_today, user.tournament_date)
        final_taper_week = is_final_taper_week(resolved_today, user.tournament_date)
        count_min, count_max = main_exercise_count_range(
            block_phase,
            category=category,
            season_period=user.season_period,
            is_tapering=tapering,
            is_final_taper_week=final_taper_week,
        )
        count = random.randint(count_min, count_max)
        forces_technical = forces_technical_archetype(
            block_phase,
            category=category,
            season_period=user.season_period,
            is_tapering=tapering,
            is_final_taper_week=final_taper_week,
        )

        preferred_skill_ids = await self._user_skill_preferences.list_skill_ids_for_user(user.id)
        priority_exercise_ids = await self._skills.list_tagged_exercise_ids(
            exercise_ids=[exercise.id for exercise in candidates], skill_ids=preferred_skill_ids
        )
        difficulty_predicate = DIFFICULTY_PRIORITY_PREDICATES.get(block_phase)
        # Precomputed once for the whole call (not per-pattern-loop-iteration
        # below) -- see _apply_difficulty_gate's docstring for why passing
        # these in matters here specifically: this is the one caller that
        # calls it once per movement_pattern, not once total.
        primary_stats = await self._exercises.list_primary_target_stats(
            [exercise.id for exercise in candidates]
        )
        user_stats = {
            stat.stat_type: stat for stat in await self._progress.list_user_stats(user.id)
        }

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

        # Same bulk-fetch shape as patterns_by_exercise above, for
        # _apply_muscle_balance below (Stage 2.1: a weighted list per
        # exercise now, not one Exercise.muscle_group column).
        muscle_groups_by_exercise = await self._exercises.list_muscle_groups_by_exercise(
            [exercise.id for exercise in candidates]
        )

        # Phase: П.3 variant stability, Stage 2.4: keyed by (pattern,
        # archetype) now -- see UserMovementPatternVariantRepository.
        existing_pins: dict[
            tuple[MovementPattern, StimulusType | None], UserMovementPatternVariant
        ] = {}
        if training_block is not None:
            existing_pins = await self._variants.list_for_user_category(user.id, category)

        picked: list[Exercise] = []
        picked_ids: set[uuid.UUID] = set()

        async def pick_for_pattern(
            pattern: MovementPattern,
            *,
            archetype: StimulusType | None,
            stimulus_preference: frozenset[StimulusType] | None = None,
            prefer_unilateral: bool = False,
            use_muscle_context: bool = False,
            bypass_gate_for_stimulus: bool = False,
        ) -> Exercise | None:
            """One role's attempt at filling a single slot from `pattern`.
            Returns the picked Exercise (already appended to `picked`), or
            None if the slot budget is spent or the pattern has no
            candidates left. archetype is the resolved pin key for
            ARCHETYPE_ELIGIBLE_PATTERNS, None for every other pattern
            (identical to pre-2.4 behavior there). stimulus_preference is
            the corresponding *soft* narrowing -- {archetype} for roles
            2-3, {POWER, SKILL} for role 1's explosive pool, unset for
            role 4 except the one guaranteed pattern (see
            bypass_gate_for_stimulus below).
            """
            if len(picked) >= count:
                return None
            # A multi-tagged exercise can appear under more than one
            # pattern's bucket -- exclude whatever's already picked so the
            # same exercise never fills two slots in one main block.
            pool = [e for e in by_pattern.get(pattern, ()) if e.id not in picked_ids]
            if not pool:
                return None
            # Pre-gate snapshot -- only used by the guarantee's own
            # bypass_gate_for_stimulus fallback below; every other caller
            # ignores this.
            raw_pool = pool

            pool, gate_exhausted = await self._apply_difficulty_gate(
                pool,
                user,
                context=f"main/{category}/{pattern}/{archetype}",
                user_stats=user_stats,
                primary_stats=primary_stats,
            )

            if difficulty_predicate is not None and not gate_exhausted:
                pool = [e for e in pool if difficulty_predicate(e)] or pool

            existing_pin = existing_pins.get((pattern, archetype))
            pinned_exercise = None
            if existing_pin is not None:
                pinned_exercise = next((e for e in pool if e.id == existing_pin.exercise_id), None)

            use_pin = False
            escalate_difficulty = False
            if pinned_exercise is not None and training_block is not None:
                same_block = existing_pin.block_number == training_block.block_number
                hold_through_deload = training_block.is_macrocycle_deload
                use_pin = same_block or hold_through_deload
                # 2026-09-17 fix (audit round 1 item #1), extended
                # 2026-09-19 (audit round 3 item #4) to squat/hip_hinge/
                # push/pull too -- see _SESSION_CAP_ROTATED_PATTERNS' own
                # comment for the "why". A same-block pin otherwise holds
                # for the whole block -- up to PHASE_CALENDAR_CEILING_WEEKS,
                # the direct cause of the "same exercise for weeks/months"
                # complaint. Force a rotation to a fresh candidate once the
                # pin has been genuinely reused ROTATION_SESSION_LIMIT times
                # in a row, same as the bodyweight-escalation break below,
                # never during a deload-hold.
                if use_pin and not hold_through_deload and pattern in _SESSION_CAP_ROTATED_PATTERNS:
                    if (existing_pin.times_chosen or 0) >= ROTATION_SESSION_LIMIT:
                        use_pin = False
                # Stage 2.6 (2026-08-20 planning session): double
                # progression has nowhere to go for a tracks_weight=false
                # exercise once reps hit the top of the range with good
                # feedback -- WeightSuggestionService.suggest_weight
                # returns None outright for those, so it would otherwise
                # just cycle at rep_range_max forever. Break even a
                # same-block pin so the fresh pick below can escalate to a
                # harder same-pattern variant instead. Never during a
                # deload-hold -- a scheduled recovery block isn't when to
                # push harder, same reasoning as the deload floor
                # elsewhere in this system.
                if use_pin and not hold_through_deload and not pinned_exercise.tracks_weight:
                    if await self._reps_suggestions.is_stuck_at_ceiling(user, pinned_exercise):
                        use_pin = False
                        escalate_difficulty = True

                # 2026-09-19 audit round 3 item #3: a reused pin (same_block
                # or hold_through_deload above) never consulted
                # stimulus_preference at all -- that filter only runs in the
                # fresh-pick branch below. Role 4's accessory patterns get
                # pinned and then held for a whole training block (Phase
                # П.3), so once ANY non-preferred exercise wins a pin,
                # guarantee_endurance's ENDURANCE ask for that same pattern
                # silently never gets a chance to apply again until the pin
                # breaks for an unrelated reason -- confirmed live: a
                # full-year simulation with guarantee_endurance=True landed
                # an ENDURANCE exercise in MAIN only 2/52, 0/52, 4/52 weeks
                # across 3 equipment scenarios (vs. 38-45/52 for
                # guarantee_locomotion, which only works because LOCOMOTION
                # itself usually already satisfies it directly, no pin-break
                # needed). Same fix also closes a dormant, unrelated gap for
                # role 1's POWER/SKILL pool, which shares this same
                # archetype=None pin key with role 4's accessory picks on
                # whichever explosive pattern role 1 doesn't win that day.
                # stimulus_type is None (uncatalogued exercise) is
                # deliberately NOT treated as a mismatch here, same leniency
                # is_genuine already gives it below -- only a real,
                # classified-but-wrong stimulus breaks the pin. Never during
                # a deload-hold, same reasoning as every check above.
                if (
                    use_pin
                    and not hold_through_deload
                    and stimulus_preference is not None
                    and pinned_exercise.stimulus_type is not None
                    and pinned_exercise.stimulus_type not in stimulus_preference
                ):
                    use_pin = False

            row = existing_pin
            if use_pin:
                choice = pinned_exercise
                if existing_pin.block_number != training_block.block_number:
                    # Deload-hold: keep the variant, just bump the bookmark
                    # so rotation resumes at the next non-deload boundary.
                    existing_pin.block_number = training_block.block_number
            else:
                stat_pool = pool
                # A real rotation boundary (not a first-ever pin, not a
                # deload-hold) -- exclude the outgoing variant so the
                # change is guaranteed, not just possible by luck.
                if pinned_exercise is not None and len(pool) > 1:
                    stat_pool = [e for e in pool if e.id != existing_pin.exercise_id] or pool

                if escalate_difficulty:
                    stat_pool = self._tier_by_escalated_difficulty(stat_pool, pinned_exercise)

                if stimulus_preference is not None:
                    preferred = [e for e in stat_pool if e.stimulus_type in stimulus_preference]
                    if not preferred and bypass_gate_for_stimulus:
                        # 2026-09-20 audit round 3 item #3 (continuation):
                        # confirmed live -- a player with a genuinely weak
                        # stat (here ENDURANCE at 17.76) had the difficulty
                        # gate cap every single ENDURANCE-tagged exercise
                        # in the whole catalog out of reach (the easiest
                        # one is difficulty_level=2, their cap allowed only
                        # 1), silently defeating guarantee_endurance's
                        # entire purpose -- it exists specifically FOR
                        # players weak in the stimulus it guarantees, so
                        # "too weak to unlock it" can never be an
                        # acceptable reason for it not to fire. Bypasses
                        # the gate for this one guaranteed slot only
                        # (never for role 1-3's own stimulus_preference,
                        # which don't pass bypass_gate_for_stimulus) --
                        # picks the single LEAST difficult genuine match
                        # from the pre-gate pool, still real content, just
                        # not respecting the normal cap this once.
                        ungated_preferred = [
                            e for e in raw_pool if e.stimulus_type in stimulus_preference
                        ]
                        if ungated_preferred:
                            easiest = min(e.difficulty_level for e in ungated_preferred)
                            preferred = [e for e in ungated_preferred if e.difficulty_level == easiest]
                    stat_pool = preferred or stat_pool

                skill_pool = [e for e in stat_pool if e.id in priority_exercise_ids] or stat_pool

                if prefer_unilateral:
                    skill_pool = [e for e in skill_pool if e.is_unilateral] or skill_pool

                if use_muscle_context:
                    loaded = set()
                    for already_picked in picked:
                        loaded |= muscle_groups_by_exercise.get(already_picked.id, set())
                    skill_pool = self._apply_muscle_balance(
                        skill_pool, loaded, muscle_groups_by_exercise
                    )

                choice = random.choice(skill_pool)

                # A fallback pick (archetype-eligible pattern, no genuine
                # stimulus_type match in the pool) must NOT be pinned the
                # same way a genuine one is -- pinning it would freeze this
                # exact fallback for the rest of the training block (weeks),
                # even once the catalog gains a real match, since a pinned
                # row is only ever reconsidered at a block boundary. Leaving
                # it unpinned means every future session retries the real
                # archetype search fresh, and a still-missing archetype
                # degrades to "a new random fallback each time" rather than
                # "the same one forever". Non-archetype patterns (archetype
                # is None, role 4) have no such concept -- every fresh pick
                # there is pinned as before.
                is_genuine = (
                    archetype is None
                    or choice.stimulus_type is None
                    or choice.stimulus_type == archetype
                )
                if training_block is not None and is_genuine:
                    if row is not None:
                        row.exercise_id = choice.id
                        row.block_number = training_block.block_number
                    else:
                        row = UserMovementPatternVariant(
                            user_id=user.id,
                            category=category,
                            movement_pattern=pattern,
                            archetype=archetype,
                            exercise_id=choice.id,
                            block_number=training_block.block_number,
                        )
                        self._session.add(row)
                        existing_pins[(pattern, archetype)] = row
                elif not is_genuine:
                    # Don't let a stale pin from an earlier block masquerade
                    # as "current" either -- row is None here unless this
                    # pattern had an old pin that fell out of same_block
                    # scope, in which case it just stays exactly as stale
                    # as it already was.
                    row = None

            if training_block is not None and archetype is not None and row is not None:
                # Only a genuine match claims the archetype as "done" --
                # see the pick_for_pattern/model docstrings on why a
                # fallback pick must not.
                if choice.stimulus_type == archetype:
                    row.last_chosen_at = resolved_today

            if training_block is not None and pattern in _SESSION_CAP_ROTATED_PATTERNS and row is not None:
                # 2026-09-17 fix (audit round 1 item #1): times_chosen is
                # the same-variant-in-a-row counter the rotation-limit check
                # above reads. use_pin=True means this session is another
                # consecutive rerun of the same pin -- bump it; any fresh
                # pick (rotation-forced, first-ever, or a genuine block
                # boundary) restarts the count at this session's own use.
                # For an archetype-eligible pattern (round 3 item #4), `row`
                # here is already the specific (pattern, archetype) row --
                # e.g. squat/POWER's counter never touches squat/STRENGTH's.
                row.times_chosen = (existing_pin.times_chosen or 0) + 1 if use_pin else 1

            picked.append(choice)
            picked_ids.add(choice.id)
            return choice

        # Role 1: explosive/skill, while fresh.
        explosive_patterns = list(_EXPLOSIVE_PATTERNS)
        random.shuffle(explosive_patterns)
        used_role1_pattern: MovementPattern | None = None
        for pattern in explosive_patterns:
            choice = await pick_for_pattern(
                pattern,
                archetype=None,
                stimulus_preference=frozenset({StimulusType.POWER, StimulusType.SKILL}),
            )
            if choice is not None:
                used_role1_pattern = pattern
                break

        # Roles 2-3: lower-body then upper-body strength, each pattern
        # resolving its own day archetype independently.
        for role_patterns, prefer_unilateral in (
            (list(_LOWER_BODY_PATTERNS), True),
            (list(_UPPER_BODY_PATTERNS), False),
        ):
            random.shuffle(role_patterns)
            for pattern in role_patterns:
                if forces_technical:
                    archetype = StimulusType.SKILL
                elif archetype_rotation is not None and pattern in archetype_rotation:
                    # Batch-wide round-robin (see _build_archetype_rotation):
                    # decided ONCE per pattern before this whole week's days
                    # started building, so a pattern can't monopolize
                    # several consecutive days the way re-deriving
                    # choose_archetype against progressively-updated
                    # last_chosen_at would (see initial_rotation_order's
                    # docstring). Never advanced during a forces_technical
                    # override, same as last_chosen_at itself.
                    archetype = next(archetype_rotation[pattern])
                else:
                    pattern_candidates = PATTERN_ARCHETYPES[pattern]
                    last_chosen_at = {
                        candidate: existing_pins[(pattern, candidate)].last_chosen_at
                        for candidate in pattern_candidates
                        if (pattern, candidate) in existing_pins
                    }
                    archetype = choose_archetype(last_chosen_at, pattern_candidates)
                await pick_for_pattern(
                    pattern,
                    archetype=archetype,
                    stimulus_preference=frozenset({archetype}),
                    prefer_unilateral=prefer_unilateral,
                )

        # Role 4: accessories/core -- every remaining pattern (role 1's
        # winning pattern, if any, is already excluded so it's never
        # reused for a second, different exercise this session).
        used_patterns = set(ARCHETYPE_ELIGIBLE_PATTERNS)
        if used_role1_pattern is not None:
            used_patterns.add(used_role1_pattern)
        accessory_patterns = [pattern for pattern in MovementPattern if pattern not in used_patterns]
        random.shuffle(accessory_patterns)

        # Guaranteed endurance/locomotion slot (2026-09-18 audit round 2
        # item #4) -- see this method's own docstring for the full
        # reasoning. Both guarantees are resolved against the full
        # (already-shuffled) accessory_patterns list, LOCOMOTION included
        # even when the skating guarantee already moved it to the front,
        # so the two can fold onto a single slot when it's also the (or
        # an) ENDURANCE-stimulus carrier -- never two separately-reserved
        # slots for what the catalog can satisfy in one.
        priority_patterns: list[MovementPattern] = []
        if guarantee_locomotion and MovementPattern.LOCOMOTION in accessory_patterns:
            priority_patterns.append(MovementPattern.LOCOMOTION)

        stimulus_pref_by_pattern: dict[MovementPattern, frozenset[StimulusType]] = {}
        if guarantee_endurance:
            endurance_capable_patterns = [
                pattern for pattern in accessory_patterns
                if any(
                    exercise.stimulus_type == StimulusType.ENDURANCE
                    for exercise in by_pattern.get(pattern, ())
                )
            ]
            if endurance_capable_patterns:
                endurance_pattern = random.choice(endurance_capable_patterns)
                stimulus_pref_by_pattern[endurance_pattern] = frozenset({StimulusType.ENDURANCE})
                if endurance_pattern not in priority_patterns:
                    priority_patterns.append(endurance_pattern)

        for pattern in priority_patterns:
            accessory_patterns.remove(pattern)
        accessory_patterns = priority_patterns + accessory_patterns

        guaranteed_exercise_ids: set[uuid.UUID] = set()
        for pattern in accessory_patterns:
            choice = await pick_for_pattern(
                pattern,
                archetype=None,
                stimulus_preference=stimulus_pref_by_pattern.get(pattern),
                use_muscle_context=True,
                # Only ever has an effect when stimulus_preference above is
                # actually set, i.e. only for the one pattern the guarantee
                # itself targeted this call -- see pick_for_pattern's own
                # comment on why the guarantee specifically needs this.
                bypass_gate_for_stimulus=True,
            )
            if choice is None:
                continue
            if guarantee_locomotion and pattern == MovementPattern.LOCOMOTION:
                guaranteed_exercise_ids.add(choice.id)
            if pattern in stimulus_pref_by_pattern and choice.stimulus_type == StimulusType.ENDURANCE:
                guaranteed_exercise_ids.add(choice.id)

        # Final coherence pass (Stage 2.4, 2026-08-20 planning session):
        # role 4's own muscle-balance check only sees the pool *at the
        # moment each of its slots is filled* -- it can't know a *later*
        # role-4 pick will also load the same muscle group, and it's a
        # soft preference that keeps the repeat outright when avoiding it
        # would leave a slot empty (see _apply_muscle_balance's own
        # docstring). This is the whole-session hindsight check the plan
        # asked for: "не более N упражнений на одну мышцу", with a
        # point-fix in the offending pattern's own pool rather than a
        # full reassembly. guaranteed_exercise_ids (2026-09-18 audit round
        # 2 item #4) are exempted from being swapped out here -- counted
        # toward the overload same as anything else, just never the fix.
        picked = self._enforce_muscle_group_cap(
            picked, patterns_by_exercise, by_pattern, muscle_groups_by_exercise,
            protected_exercise_ids=guaranteed_exercise_ids,
        )

        return picked

    @staticmethod
    def _enforce_muscle_group_cap(
        picked: list[Exercise],
        patterns_by_exercise: dict[uuid.UUID, list[MovementPattern]],
        by_pattern: dict[MovementPattern, list[Exercise]],
        muscle_groups_by_exercise: dict[uuid.UUID, set[MuscleGroup]],
        *,
        protected_exercise_ids: frozenset[uuid.UUID] | set[uuid.UUID] = frozenset(),
    ) -> list[Exercise]:
        """_pick_main's whole-session hindsight pass, run once after every
        role is filled -- see that call site's own comment for why this
        exists on top of (not instead of) role 4's per-pick
        _apply_muscle_balance. Bounded to len(picked) passes (each
        successful fix strictly reduces the offending group's count by one,
        so this always terminates well before that bound in practice) --
        one full rescan per fix rather than trying to reason about which
        other groups a substitution could newly push over cap.

        Point-fix target: for the muscle group currently over
        MAX_EXERCISES_PER_MUSCLE_GROUP, tries each contributing exercise in
        session order (earlier role-1-3 picks first) and substitutes the
        first one whose OWN movement_pattern pool actually has an unused
        candidate -- deliberately not restricted to "the last one added",
        since an earlier pick can be the fixable one precisely because
        nothing was loaded yet when it was chosen (see the pattern this
        catches in its own docstring below). Prefers a substitute that
        doesn't ALSO carry the offending group; if every remaining
        candidate does, still swaps to whichever was found (a same-group
        swap after a fix pass reduces the surrounding pool, so a later
        pass may still resolve it) rather than declaring the pattern a
        dead end. If no pattern in the offending group can be fixed at
        all, leaves the session as-is -- same "never leave a slot empty
        over a soft/best-effort concern" convention as every layer above
        this one; a residual pile-up from genuine catalog scarcity is
        honest, not silently hidden by dropping a slot.

        protected_exercise_ids (2026-09-18 audit round 2 item #4): exercises
        _pick_main's guarantee_endurance/guarantee_locomotion actually
        placed -- skipped as a *substitution candidate* (never picked to be
        swapped OUT), but still fully counted in `counts` above, same as
        any other exercise. A muscle group that's only over cap because of
        a protected exercise stays honestly over cap rather than silently
        losing the guarantee to fix it -- this function was already willing
        to leave a residual pile-up when no substitute existed at all; this
        is the same acceptance, just for a case where a substitute exists
        but isn't allowed to be used.
        """
        picked_ids = {e.id for e in picked}
        for _ in range(len(picked)):
            counts: dict[MuscleGroup, list[Exercise]] = defaultdict(list)
            for exercise in picked:
                for group in muscle_groups_by_exercise.get(exercise.id, ()):
                    counts[group].append(exercise)
            offending = next(
                ((group, exs) for group, exs in counts.items() if len(exs) > MAX_EXERCISES_PER_MUSCLE_GROUP),
                None,
            )
            if offending is None:
                break
            offending_group, offenders = offending

            fixed = False
            for offender in offenders:
                if offender.id in protected_exercise_ids:
                    continue
                pool: list[Exercise] = []
                for pattern in patterns_by_exercise.get(offender.id, ()):
                    pool.extend(by_pattern.get(pattern, ()))
                substitutes = [e for e in pool if e.id not in picked_ids]
                if not substitutes:
                    continue
                replacement = next(
                    (
                        e for e in substitutes
                        if offending_group not in muscle_groups_by_exercise.get(e.id, set())
                    ),
                    substitutes[0],
                )
                index = picked.index(offender)
                picked[index] = replacement
                picked_ids.discard(offender.id)
                picked_ids.add(replacement.id)
                fixed = True
                break

            if not fixed:
                break

        return picked

    async def _pick_main_replacement(
        self,
        category: ExerciseCategory,
        user: User,
        block_phase: BlockPhase,
        *,
        role_patterns: frozenset[MovementPattern],
        exclude_ids: set[uuid.UUID],
        loaded_muscle_groups: set[MuscleGroup],
    ) -> Exercise | None:
        """Stage 1.5 (2026-08-20 planning session): the MAIN half of
        replace_block_exercise's manual single-slot swap -- a deliberately
        simpler, one-shot cousin of _pick_main's pick_for_pattern (no
        variant-pin bookkeeping, no archetype resolution: this is an ad-hoc
        override of one exercise in one already-assembled session, not a
        change to the automatic rotation's own state). Layers, in order:
        readiness/difficulty gate (same as pick_for_pattern) -> narrow to
        `role_patterns` (falls back to the gated pool if nothing matches --
        e.g. an under-tagged catalog corner) -> _apply_muscle_balance
        against every muscle group already loaded elsewhere in today's
        session (falls back the same way). exclude_ids always includes at
        least the outgoing exercise and every other exercise already in
        this session, so the swap can't just hand back the same pick or
        create a duplicate.
        """
        candidates = await self._exercises.list_for_assembly(
            phase=TrainingPhase.MAIN, user=user, category=category
        )
        candidates = [e for e in candidates if e.id not in exclude_ids]
        if not candidates:
            return None

        candidates, gate_exhausted = await self._apply_difficulty_gate(
            candidates, user, context=f"replace/main/{category}"
        )
        difficulty_predicate = DIFFICULTY_PRIORITY_PREDICATES.get(block_phase)
        if difficulty_predicate is not None and not gate_exhausted:
            candidates = [e for e in candidates if difficulty_predicate(e)] or candidates

        patterns_by_id = await self._exercises.list_movement_patterns_by_exercise(
            [e.id for e in candidates]
        )
        pool = [
            e for e in candidates if role_patterns.intersection(patterns_by_id.get(e.id, ()))
        ] or candidates

        if loaded_muscle_groups:
            muscle_groups_by_id = await self._exercises.list_muscle_groups_by_exercise(
                [e.id for e in pool]
            )
            pool = self._apply_muscle_balance(pool, loaded_muscle_groups, muscle_groups_by_id)

        return random.choice(pool)

    @staticmethod
    def _apply_muscle_balance(
        pool: list[Exercise],
        loaded_muscle_groups: set[MuscleGroup],
        muscle_groups_by_exercise: dict[uuid.UUID, set[MuscleGroup]],
    ) -> list[Exercise]:
        """Role 4 (accessories/core) only, Stage 2.4: soft anatomical
        variety rule, aware of every muscle group loaded anywhere earlier
        in *this session* (roles 1-3, plus role 4's own picks so far as it
        goes) -- generalized from the pre-2.4 version's "last two picks
        only" check, now that role ordering means role 4 genuinely knows
        the full session context by the time it runs.

        Fires whenever `loaded_muscle_groups` is non-empty and excludes
        any candidate whose own muscle-group set overlaps it, applied
        *within* whatever pool the skill-priority step above already
        narrowed to -- so a user's SkillTag priority always wins a
        conflict, this never reaches back into the wider stat pool to
        find variety the priority pool doesn't have. Exercises tagged
        with no muscle group at all (see ExerciseMuscleGroup's docstring
        on what an empty set means) never trigger or get filtered by this.

        Falls back to the untouched pool whenever avoiding overlap would
        empty it, so a main slot is never left unfilled for this reason.
        """
        if not loaded_muscle_groups:
            return pool
        varied = [
            e for e in pool if not (muscle_groups_by_exercise.get(e.id, set()) & loaded_muscle_groups)
        ]
        return varied or pool

    @staticmethod
    def _tier_by_escalated_difficulty(pool: list[Exercise], outgoing: Exercise) -> list[Exercise]:
        """Bodyweight-escalation tiering (Stage 2.6, extended 2026-09-18
        audit round 2 item #1): shared by pick_for_pattern's own
        escalate_difficulty branch and escalate_ceiling_variant_for_week's
        week-patch. Three tiers, same "narrow, fall back if empty" shape as
        every other preference layer in this file:

          1. Strictly higher difficulty_level than `outgoing` -- a genuine
             step up, the normal case.
          2. No such candidate (a real difficulty ceiling for this pattern/
             stimulus -- common for push/pull bodyweight work, which the
             catalog only has a couple of difficulty tiers for) -> a
             *different* same-difficulty variant instead, so the swap is
             still lateral variety, never a downgrade. `outgoing` itself is
             always excluded here regardless of whether `pool` already did
             -- the point of this tier existing at all is to never silently
             hand back the exercise that's already stuck.
          3. Nothing else in `pool` either (a genuine catalog gap, or
             `pool` had nothing but `outgoing` to begin with) -> the
             unfiltered `pool`, or `outgoing` itself as the absolute last
             resort so a caller never has to handle an empty result.
        """
        higher = [e for e in pool if e.difficulty_level > outgoing.difficulty_level]
        if higher:
            return higher
        same = [e for e in pool if e.difficulty_level == outgoing.difficulty_level and e.id != outgoing.id]
        if same:
            return same
        return pool or [outgoing]

    async def _apply_difficulty_gate(
        self,
        candidates: list[Exercise],
        user: User,
        *,
        context: str,
        user_stats: dict[TargetStat, UserStat] | None = None,
        primary_stats: dict[uuid.UUID, TargetStat] | None = None,
    ) -> tuple[list[Exercise], bool]:
        """Difficulty ceiling, split by category (2026-08-18 planning
        session -- see app.core.stat_difficulty's module docstring for the
        full "why"):

          - ON_ICE: unchanged, still User.level via max_difficulty_for_level
            -- deliberately untouched pending a separate pass at the on-ice
            assessment/stat pipeline.
          - OFF_ICE: gated per-exercise by the *user's* effective (decay-
            adjusted, see app.services.stat_service.get_effective_value)
            value of that exercise's own primary (order=0) target_stat, via
            app.core.stat_difficulty.max_difficulty_for_stat -- a strong-
            legged, weak-armed user can be eligible for a heavy squat and
            still capped on a heavy bench press in the same pick. An
            exercise with no primary target_stat classified yet gets
            UNCLASSIFIED_EXERCISE_CAP rather than a free pass.

        Both branches still apply the Phase 5 structural overload brake
        (effective_difficulty_cap) on top.

        2026-09-17 fix (audit item #2): a pool that comes up empty at each
        exercise's own exact cap used to fall straight through to the
        ENTIRE unfiltered `candidates` range -- e.g. a 20-40 stat (real
        cap=2) with zero difficulty<=2 candidates for this specific
        pattern/stat combination (a catalog gap, not a readiness fact)
        degraded all the way to "any difficulty including 5", not the next
        rung up. Now relaxes one difficulty step at a time (cap+1, cap+2,
        ...) instead, so a real cap=2 user who hits a content gap lands on
        the closest actually-available difficulty rather than the ceiling.
        Since every Exercise.difficulty_level is already <= MAX_DIFFICULTY_
        LEVEL, this climb is guaranteed to find something as long as
        `candidates` itself is non-empty -- the true last-resort fallback
        (returned exhausted=True) is only reachable if it isn't, which
        every real caller already guards against before calling this.

        Returns (gated_pool, exhausted). exhausted is True only for that
        true last-resort case. A caller that also applies a phase
        preference on top (DIFFICULTY_PRIORITY_PREDICATES -- "prefer the
        heaviest" in INTENSIFICATION, "prefer the lightest" in DELOAD)
        MUST skip that preference when exhausted=True: applying an active
        search for the heaviest/lightest remaining option on top of an
        already-degraded emergency pick is exactly the compounding bug
        the audit reported (a 20-40 user ending up with a difficulty-5
        squat). Every call site in this file already does this.

        user_stats/primary_stats let a caller that loops per-candidate-pool
        multiple times in one assembly (only _pick_main does, once per
        movement_pattern) fetch both once up front and pass them in, rather
        than re-querying the same user's stats and the same exercises'
        primary target_stats on every loop iteration. Callers that pick
        once (_pick_single/_pick_sequence/_pick_warmup_complex/
        _pick_mental_prep) can omit both and this fetches them itself --
        only ever queries for whichever of the two categories is actually
        present in `candidates`.
        """
        if not candidates:
            return [], False

        throttle = user.difficulty_throttle_steps
        on_ice = [e for e in candidates if e.category == ExerciseCategory.ON_ICE]
        off_ice = [e for e in candidates if e.category == ExerciseCategory.OFF_ICE]

        base_caps: dict[uuid.UUID, int] = {}

        if on_ice:
            level_cap = effective_difficulty_cap(max_difficulty_for_level(user.level), throttle)
            for exercise in on_ice:
                base_caps[exercise.id] = level_cap

        if off_ice:
            if primary_stats is None:
                primary_stats = await self._exercises.list_primary_target_stats(
                    [e.id for e in off_ice]
                )
            if user_stats is None:
                user_stats = {
                    stat.stat_type: stat for stat in await self._progress.list_user_stats(user.id)
                }
            now = datetime.now(timezone.utc)
            for exercise in off_ice:
                stat_type = primary_stats.get(exercise.id)
                if stat_type is None:
                    stat_cap = UNCLASSIFIED_EXERCISE_CAP
                else:
                    user_stat = user_stats.get(stat_type)
                    value = get_effective_value(user_stat, now) if user_stat is not None else 0.0
                    stat_cap = max_difficulty_for_stat(value)
                base_caps[exercise.id] = effective_difficulty_cap(stat_cap, throttle)

        for extra in range(MAX_DIFFICULTY_LEVEL):
            capped = [
                e
                for e in candidates
                if e.difficulty_level <= min(MAX_DIFFICULTY_LEVEL, base_caps[e.id] + extra)
            ]
            if capped:
                if extra:
                    logger.warning(
                        "Readiness cap relaxed by %d for %s (user_id=%s, level=%s) -- "
                        "no exercise at the exact cap, closest available difficulty used instead",
                        extra,
                        context,
                        user.id,
                        user.level,
                    )
                return capped, False

        logger.warning(
            "No exercises at any difficulty available for %s "
            "(user_id=%s, level=%s -- irrelevant off-ice, see UserStat instead) -- "
            "falling back to the full unfiltered candidate list so the plan isn't left empty",
            context,
            user.id,
            user.level,
        )
        return candidates, True

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

        Equipment (Stage 2.2, personal-gear split 2026-08-22):
        list_for_assembly's own has_gym_access/owned-items subset check is
        already correct per member, but it's a single-user query -- this
        needs the same check applied to *every* member and intersected, so
        it's done here in Python instead: eligible only if for each
        member, every item the exercise requires is covered -- either in
        GYM_COVERED_ITEMS while that member has gym access, or in that
        member's own owned set (PERSONAL_GEAR_ITEMS like a hockey stick
        are never covered by gym access, same as list_for_assembly). An
        exercise requiring nothing is eligible for everyone regardless,
        same "gym access is a bypass of gym equipment, not everything"
        contract list_for_assembly uses.

        Difficulty (2026-08-18): per exercise, capped at the *weakest*
        member's effective value of that exercise's own primary
        target_stat, via app.core.stat_difficulty.max_difficulty_for_stat
        -- same readiness-based gate _apply_difficulty_gate uses for a
        personal plan's off-ice picks, just minimized across every member
        instead of read from one user. Never relaxed past that even if a
        pattern ends up with no eligible candidates (unlike
        _apply_difficulty_gate's last-resort fallback for personal plans,
        which would relax the cap rather than leave a slot unfilled).
        Overloading someone is worse here than a shorter suggested list.
        An exercise with no primary target_stat classified yet gets
        UNCLASSIFIED_EXERCISE_CAP, same as a personal plan's off-ice pick.
        """
        if not members:
            return []

        candidates = await self._exercises.list_exercises(
            category=ExerciseCategory.OFF_ICE, phase=TrainingPhase.MAIN
        )
        required_by_exercise = await self._exercises.list_equipment_items_by_exercise(
            [exercise.id for exercise in candidates]
        )
        owned_by_member = await self._exercises.list_owned_equipment_by_user(
            [m.id for m in members]
        )
        eligible = [
            exercise
            for exercise in candidates
            if all(
                required_by_exercise.get(exercise.id, set())
                <= owned_by_member.get(member.id, set())
                | (GYM_COVERED_ITEMS if member.has_gym_access else set())
                for member in members
            )
        ]

        primary_stats = await self._exercises.list_primary_target_stats(
            [exercise.id for exercise in eligible]
        )
        member_stats: list[dict[TargetStat, UserStat]] = [
            {stat.stat_type: stat for stat in await self._progress.list_user_stats(member.id)}
            for member in members
        ]
        now = datetime.now(timezone.utc)

        def _cap_for(exercise: Exercise) -> int:
            stat_type = primary_stats.get(exercise.id)
            if stat_type is None:
                return UNCLASSIFIED_EXERCISE_CAP
            caps = []
            for stats in member_stats:
                user_stat = stats.get(stat_type)
                value = get_effective_value(user_stat, now) if user_stat is not None else 0.0
                caps.append(max_difficulty_for_stat(value))
            return min(caps)

        eligible = [exercise for exercise in eligible if exercise.difficulty_level <= _cap_for(exercise)]

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
        main_muscle_groups = await self._muscle_groups_union(exercise_ids)
        warmup_exercises = await self._pick_warmup_complex(
            ExerciseCategory.OFF_ICE,
            user,
            block_phase,
            preferred_patterns=main_patterns,
            preferred_muscle_groups=main_muscle_groups,
        )
        cooldown_count = min(_COOLDOWN_SEQUENCE_MAX, len(main_patterns)) or _COOLDOWN_SEQUENCE_MAX
        cooldown_exercises = await self._pick_sequence(
            TrainingPhase.COOLDOWN,
            ExerciseCategory.OFF_ICE,
            user,
            block_phase,
            count=cooldown_count,
            preferred_patterns=main_patterns,
            preferred_muscle_groups=main_muscle_groups,
        )

        # Same running-order idiom as _build_training_session -- order runs
        # across the whole session, not reset per phase.
        blocks: list[SessionBlock] = []
        for exercise in warmup_exercises:
            blocks.append(SessionBlock(phase=TrainingPhase.WARMUP, exercise_id=exercise.id, order=len(blocks)))
        for exercise_id in exercise_ids:
            blocks.append(SessionBlock(phase=TrainingPhase.MAIN, exercise_id=exercise_id, order=len(blocks)))
        for exercise in cooldown_exercises:
            blocks.append(SessionBlock(phase=TrainingPhase.COOLDOWN, exercise_id=exercise.id, order=len(blocks)))

        day_plan.training_session = TrainingSession(blocks=blocks)
        await self._session.flush()

    async def replace_block_exercise(self, block_id: uuid.UUID, user: User) -> SessionBlockRead:
        """Stage 1.5 (2026-08-20 planning session, "тренажёр занят"): a
        manual, single-slot swap -- not a session regenerate, the point is
        replacing exactly one exercise without disturbing anything else the
        user has already seen or started. MAIN blocks substitute within the
        outgoing exercise's own role (_role_patterns_for -- explosive/
        lower-body/upper-body/accessory, matching _pick_main's own role
        split) and stay aware of every muscle group already loaded by the
        rest of today's session (_pick_main_replacement); WARMUP/COOLDOWN
        blocks substitute by movement_pattern via the existing _pick_single,
        since roles/archetypes are a MAIN-only concept there's nothing role-
        based to match on. Deliberately never touches
        UserMovementPatternVariant -- this is an ad-hoc override of one
        session, not a change to the automatic rotation's own state, so a
        later fresh assembly still rotates as if this swap never happened.
        """
        block = await self._schedule.get_session_block_with_owner(block_id)
        if block is None or block.session.day_plan.weekly_plan.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session block not found"
            )
        if block.completed_at is not None or block.skipped_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="already completed"
            )

        training_session = await self._schedule.get_training_session_with_owner(block.session_id)
        sibling_exercise_ids = [b.exercise_id for b in training_session.blocks if b.id != block.id]
        exclude_ids = {block.exercise_id, *sibling_exercise_ids}

        category = block.exercise.category
        training_block = await self._training_block_service.get_or_create_and_resolve(user.id)
        block_phase = await self._overload_service.apply_brakes(user, training_block.phase)
        current_patterns = set(await self._exercises.list_movement_patterns(block.exercise_id))

        if block.phase == TrainingPhase.MAIN:
            role_patterns = _role_patterns_for(current_patterns)
            loaded_muscle_groups = await self._muscle_groups_union(sibling_exercise_ids)
            new_exercise = await self._pick_main_replacement(
                category,
                user,
                block_phase,
                role_patterns=role_patterns,
                exclude_ids=exclude_ids,
                loaded_muscle_groups=loaded_muscle_groups,
            )
        else:
            new_exercise = await self._pick_single(
                block.phase,
                category,
                user,
                block_phase,
                preferred_patterns=current_patterns,
                exclude_ids=exclude_ids,
            )

        if new_exercise is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="No substitute exercise available"
            )

        block.exercise_id = new_exercise.id
        await self._session.commit()
        target_stats = await self._exercises.list_target_stats(new_exercise.id)
        return SessionBlockRead(
            id=block.id,
            phase=block.phase,
            order=block.order,
            completed_at=block.completed_at,
            skipped_at=block.skipped_at,
            exercise=exercise_to_read(new_exercise, target_stats),
        )

    @staticmethod
    def _untouched_future_day_plans(weekly_plan: WeeklyPlan, today: date) -> list[DayPlan]:
        """Shared by every same-week patcher (escalate_ceiling_variant_for_week,
        patch_week_for_eligibility_change): "not yet started" = day.date
        strictly after the user's today (never today's own day -- that's
        whatever's currently in progress) AND every block in that day's
        session is still unresolved. A day that's only partially touched
        (e.g. warmup already logged ahead of time) is left alone entirely,
        same caution as _patch_weekly_plan's own "already begun" guard --
        these patchers only ever mutate exercise_id/blocks in place, never
        rebuild a day, but the same all-or-nothing rule still applies."""
        return [
            day_plan
            for day_plan in weekly_plan.day_plans
            if day_plan.date > today
            and day_plan.training_session is not None
            and all(
                block.completed_at is None and block.skipped_at is None
                for block in day_plan.training_session.blocks
            )
        ]

    async def patch_week_for_eligibility_change(
        self, user: User, *, today: date | None = None
    ) -> int:
        """2026-09-19 audit round 3 item #2: UserTemporaryRestrictionService.report/
        lift and UserService.replace_owned_equipment each only ever write a
        row and commit -- ExerciseRepository.list_for_assembly (equipment +
        active-restriction filtering) only ever runs at fresh day/week
        assembly, so a restriction reported (or lifted) or equipment
        added/removed mid-week never touched the days already generated for
        the current week. The restriction docstring promises "excludes ...
        for as long as it's active"; in practice that only held going
        forward. Confirmed live via a full-year/3-scenario simulation on
        the real catalog (gym scenario): a chest exercise present the week
        a restriction on it started, then correctly 0/4 weeks after --
        i.e. the forward filter genuinely works, only the already-generated
        week didn't retroactively honor it.

        One shared patcher for both triggers rather than two near-duplicate
        ones -- same principle as escalate_ceiling_variant_for_week: only
        touch SessionBlock rows in days of the CURRENT week that are still
        entirely untouched (see _untouched_future_day_plans), leave
        anything already begun exactly as it is. Two independent things it
        does, since exercise-block replacement can't undo the "puck module
        only appears at fresh assembly" gap (that's whole new blocks, not a
        swap):

        1. Any exercise now outside list_for_assembly's current pool for
           its own (phase, category) -- newly restricted, or newly missing
           required equipment -- gets swapped for a same-movement-pattern
           eligible substitute (falling back to any eligible exercise in
           that phase/category if none shares a pattern), same
           conservative "leave it if genuinely nothing else qualifies"
           rule _pick_ceiling_escalation_candidate already uses. A MAIN
           block's UserMovementPatternVariant pin (if any) moves with it,
           mirroring escalate_ceiling_variant_for_week -- _pick_main's own
           pin-reuse already silently self-heals this at the next fresh
           assembly (a restricted pinned exercise simply isn't in `pool`
           there so the pin gets overwritten), this just makes the *current*
           week's already-materialized blocks agree with that sooner rather
           than only from next week.
        2. A hockey stick added mid-week: an OFF_ICE day untouched this
           week that has no TrainingPhase.PUCK blocks yet gets them
           appended now (same _pick_puck_module_exercises call
           _build_training_session uses at fresh assembly), instead of
           only from next week's generation. Symmetric removal case (stick
           taken out of inventory): a PUCK block whose exercise fails the
           equipment filter with literally no substitute in the whole
           phase (pool 1's only real case for that phase) is dropped from
           the session outright rather than left showing an exercise the
           filter itself has already vetoed -- cascade="all, delete-orphan"
           on TrainingSession.blocks handles the actual row deletion.

        Returns the number of blocks changed (edited or added/removed) --
        0 whenever nothing needed patching, including "no current week"
        and "every remaining day is already underway". Committing is the
        caller's job (UserTemporaryRestrictionService.report/lift,
        UserService.replace_owned_equipment already commit their own row
        right after calling this), same non-committing contract
        escalate_ceiling_variant_for_week already uses.

        today defaults to the user's own today (ZoneInfo(user.timezone),
        2026-09-20 audit round 3 fix), injectable purely for deterministic
        tests -- see escalate_ceiling_variant_for_week's own matching fix
        for the full reasoning (a fixed "TODAY" fixture constant used to
        silently drift out of validity the day after a test was written,
        since this method always read the real wall clock regardless).
        """
        resolved_today = today or datetime.now(ZoneInfo(user.timezone or "UTC")).date()
        weekly_plan = await self._schedule.get_current(user.id, resolved_today)
        if weekly_plan is None:
            return 0

        untouched_day_plans = self._untouched_future_day_plans(weekly_plan, resolved_today)
        if not untouched_day_plans:
            return 0

        changed = 0
        for day_plan in untouched_day_plans:
            category = _SESSION_TYPE_TO_CATEGORY.get(day_plan.session_type)
            if category is None:
                # GAME (no MAIN/regular phase split, see
                # _day_plan_to_read_schema) -- out of scope for this pass.
                continue
            session = day_plan.training_session
            changed += await self._patch_session_blocks_for_eligibility(user, category, session)
            if category == ExerciseCategory.OFF_ICE:
                changed += await self._maybe_add_puck_module_midweek(user, session)

        if changed:
            await self._session.flush()
        return changed

    async def _patch_session_blocks_for_eligibility(
        self, user: User, category: ExerciseCategory, session: TrainingSession
    ) -> int:
        blocks_by_phase: dict[TrainingPhase, list[SessionBlock]] = defaultdict(list)
        for block in session.blocks:
            blocks_by_phase[block.phase].append(block)

        changed = 0
        for phase, blocks in blocks_by_phase.items():
            eligible_pool = await self._exercises.list_for_assembly(
                phase=phase, user=user, category=category
            )
            eligible_ids = {exercise.id for exercise in eligible_pool}
            stale_blocks = [block for block in blocks if block.exercise_id not in eligible_ids]
            if not stale_blocks:
                continue

            patterns_by_exercise = await self._exercises.list_movement_patterns_by_exercise(
                [block.exercise_id for block in stale_blocks] + list(eligible_ids)
            )

            for block in stale_blocks:
                old_exercise_id = block.exercise_id
                old_patterns = set(patterns_by_exercise.get(old_exercise_id, ()))
                same_pattern_pool = [
                    exercise
                    for exercise in eligible_pool
                    if old_patterns & set(patterns_by_exercise.get(exercise.id, ()))
                ]
                replacement_pool = same_pattern_pool or eligible_pool
                if not replacement_pool:
                    if phase == TrainingPhase.PUCK:
                        # No substitute at all (typically: the stick that
                        # justified this block is gone) -- nothing legal
                        # to show here any more, unlike every other phase
                        # a session can't simply go without.
                        session.blocks.remove(block)
                        changed += 1
                    continue

                new_exercise = random.choice(replacement_pool)
                block.exercise_id = new_exercise.id
                changed += 1

                if phase == TrainingPhase.MAIN:
                    pins = await self._variants.list_for_user_exercise(user.id, old_exercise_id)
                    new_patterns = set(patterns_by_exercise.get(new_exercise.id, ()))
                    for pin in pins:
                        if pin.movement_pattern in new_patterns:
                            pin.exercise_id = new_exercise.id

        return changed

    async def _maybe_add_puck_module_midweek(self, user: User, session: TrainingSession) -> int:
        if any(block.phase == TrainingPhase.PUCK for block in session.blocks):
            return 0

        training_block = await self._training_block_service.get_or_create_and_resolve(user.id)
        block_phase = await self._overload_service.apply_brakes(user, training_block.phase)
        puck_exercises = await self._pick_puck_module_exercises(user, block_phase)
        if not puck_exercises:
            return 0

        order = len(session.blocks)
        for exercise in puck_exercises:
            session.blocks.append(
                SessionBlock(phase=TrainingPhase.PUCK, exercise_id=exercise.id, order=order)
            )
            order += 1
        return len(puck_exercises)

    async def escalate_ceiling_variant_for_week(
        self, user: User, exercise: Exercise, *, today: date | None = None
    ) -> list[CeilingEscalationRead]:
        """2026-09-18 audit round 2 item #1: SessionBlockService.complete_block's
        synchronous follow-up to a just-completed MAIN block. A
        tracks_weight=false exercise that's genuinely stuck (see
        RepsSuggestionService.is_stuck_at_ceiling) doesn't just wait for the
        next fresh day-generation to swap itself out -- create_weekly_plan
        already built every day of the current week up front, so an
        already-generated-but-not-yet-started day would otherwise keep
        showing the stuck exercise for the rest of the week. This patches
        those specific SessionBlock rows directly (exercise_id only,
        nothing else about the day) rather than regenerating the day, and
        moves the UserMovementPatternVariant pin itself so any later fresh
        assembly (next block boundary, a new week) picks up the same
        change. Returns one CeilingEscalationRead per pin actually moved --
        empty whenever escalation doesn't apply, or the catalog has no real
        substitute for a pin (see _tier_by_escalated_difficulty's
        last-resort tier landing back on `exercise` itself).

        "Not yet started" = day.date strictly after the user's today (never
        today's own day -- that's the one currently being completed) AND
        every block in that day's session is still unresolved. A day
        that's only partially touched (e.g. warmup already logged ahead of
        time) is left alone entirely, same caution as _patch_weekly_plan's
        own "already begun" guard, even though this method only ever
        touches one exercise_id at a time rather than rebuilding the day.

        Committing is the caller's job, not this method's -- every write
        here is an in-place mutation plus a single flush, so it composes
        into SessionBlockService.complete_block's own transaction instead
        of risking a patched week whose triggering block completion then
        fails to commit.

        today defaults to the user's own today (ZoneInfo(user.timezone),
        2026-09-20 audit round 3 fix), injectable purely for deterministic
        tests -- same shape as _pick_main's own `today` param. Before this
        fix, tests that pinned a fake "TODAY" constant into their fixture
        dates (to build a day that's "tomorrow" relative to that constant)
        silently started failing the day after they were written, since
        this method always read the real wall clock regardless of what the
        test's fixtures assumed "today" was.
        """
        if exercise.tracks_weight:
            return []
        if not await self._reps_suggestions.is_stuck_at_ceiling(user, exercise):
            return []

        pins = await self._variants.list_for_user_exercise(user.id, exercise.id)
        if not pins:
            return []

        resolved_today = today or datetime.now(ZoneInfo(user.timezone or "UTC")).date()
        weekly_plan = await self._schedule.get_current(user.id, resolved_today)
        if weekly_plan is None:
            return []

        untouched_day_plans = self._untouched_future_day_plans(weekly_plan, resolved_today)
        untouched_future_sessions = [day_plan.training_session for day_plan in untouched_day_plans]
        if not untouched_future_sessions:
            return []

        training_block = await self._training_block_service.get_or_create_and_resolve(user.id)
        block_phase = await self._overload_service.apply_brakes(user, training_block.phase)

        escalations: list[CeilingEscalationRead] = []
        for pin in pins:
            new_exercise = await self._pick_ceiling_escalation_candidate(
                user, block_phase, pin, exercise
            )
            if new_exercise is None or new_exercise.id == exercise.id:
                # No genuine substitute for this pin (catalog gap) -- leave
                # the pin and every SessionBlock exactly as they are rather
                # than "escalate" to the same stuck exercise.
                continue

            pin.exercise_id = new_exercise.id
            if pin.archetype is None or new_exercise.stimulus_type == pin.archetype:
                pin.last_chosen_at = resolved_today

            for training_session in untouched_future_sessions:
                for block in training_session.blocks:
                    if block.exercise_id == exercise.id:
                        block.exercise_id = new_exercise.id

            escalations.append(
                CeilingEscalationRead(
                    old_exercise_name=exercise.name, new_exercise_name=new_exercise.name
                )
            )

        if escalations:
            await self._session.flush()
        return escalations

    async def _pick_ceiling_escalation_candidate(
        self,
        user: User,
        block_phase: BlockPhase,
        pin: UserMovementPatternVariant,
        outgoing: Exercise,
    ) -> Exercise | None:
        """One pin's half of escalate_ceiling_variant_for_week -- deliberately
        simpler than pick_for_pattern's own closure (no rotation/deload-hold
        bookkeeping, the caller already resolved that this pin needs to
        move), same shape as _pick_main_replacement otherwise: readiness
        gate -> narrow to the pin's exact movement_pattern -> narrow to its
        stimulus archetype if it has one -> _tier_by_escalated_difficulty.
        """
        candidates = await self._exercises.list_for_assembly(
            phase=TrainingPhase.MAIN, user=user, category=pin.category
        )
        candidates = [e for e in candidates if e.id != outgoing.id]
        if not candidates:
            return None

        patterns_by_id = await self._exercises.list_movement_patterns_by_exercise(
            [e.id for e in candidates]
        )
        pool = [e for e in candidates if pin.movement_pattern in patterns_by_id.get(e.id, ())]
        if not pool:
            return None

        pool, gate_exhausted = await self._apply_difficulty_gate(
            pool, user, context=f"ceiling_escalation/{pin.category}/{pin.movement_pattern}"
        )
        difficulty_predicate = DIFFICULTY_PRIORITY_PREDICATES.get(block_phase)
        if difficulty_predicate is not None and not gate_exhausted:
            pool = [e for e in pool if difficulty_predicate(e)] or pool

        if pin.archetype is not None:
            pool = [e for e in pool if e.stimulus_type == pin.archetype] or pool

        tiered = self._tier_by_escalated_difficulty(pool, outgoing)
        return random.choice(tiered)

    # 2026-09-17 (audit item #3): the only session_types TrainingDiaryCard
    # ever renders for (see TrainingSessionPage.tsx) -- has_diary_entry is
    # None for every other session_type, not just False, so the frontend
    # can tell "no diary step here" apart from "diary step not done yet".
    _DIARY_ELIGIBLE_SESSION_TYPES = frozenset({DaySessionType.ON_ICE, DaySessionType.GAME})

    def _day_plan_to_read_schema(
        self,
        day: DayPlan,
        stats_by_id: dict[uuid.UUID, list[TargetStat]],
        diary_session_ids: set[uuid.UUID],
    ) -> DayPlanRead:
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
                    skipped_at=block.skipped_at,
                    exercise=exercise_to_read(
                        block.exercise, stats_by_id.get(block.exercise_id, [])
                    ),
                )
                for block in day.training_session.blocks
            ]
            has_diary_entry = (
                day.training_session.id in diary_session_ids
                if day.session_type in self._DIARY_ELIGIBLE_SESSION_TYPES
                else None
            )
            session_read = TrainingSessionRead(
                id=day.training_session.id,
                phase_split=phase_split,
                duration_seconds=duration_seconds,
                blocks=blocks_read,
                has_diary_entry=has_diary_entry,
            )
        return DayPlanRead(
            id=day.id,
            date=day.date,
            session_type=day.session_type,
            training_session=session_read,
        )

    async def _to_read_schema(self, weekly_plan: WeeklyPlan) -> WeeklyPlanRead:
        exercise_ids = [
            block.exercise_id
            for day in weekly_plan.day_plans
            if day.training_session is not None
            for block in day.training_session.blocks
        ]
        stats_by_id = await self._exercises.list_target_stats_by_exercise(exercise_ids)
        diary_candidate_ids = [
            day.training_session.id
            for day in weekly_plan.day_plans
            if day.training_session is not None
            and day.session_type in self._DIARY_ELIGIBLE_SESSION_TYPES
        ]
        diary_session_ids = await self._diary.list_session_ids_with_entries(diary_candidate_ids)

        day_reads = [
            self._day_plan_to_read_schema(day, stats_by_id, diary_session_ids)
            for day in weekly_plan.day_plans
        ]
        return WeeklyPlanRead(
            id=weekly_plan.id, week_start_date=weekly_plan.week_start_date, day_plans=day_reads
        )

    async def get_day_plan_for_date(self, user: User, target_date: date) -> DayPlanRead:
        """GET /schedule/day-plan -- a single day's plan (+ session/blocks if
        one exists) by exact date, independent of which week is "current" or
        "next" right now. Backs HomePage's activity-calendar day-detail modal:
        that calendar covers any month of history via
        GET /users/me/activity-calendar, but that endpoint only returns a
        per-day completed boolean (see DayActivity), not the block-by-block
        breakdown -- this is the other half, fetched lazily only once a
        historical day is actually tapped. Reuses
        ScheduleRepository.get_day_plan_for_date, the same lookup
        TrainingPartyService already relies on for a single (user, date)
        pair, rather than adding a second one.
        """
        day = await self._schedule.get_day_plan_for_date(user.id, target_date)
        if day is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No day plan for {target_date.isoformat()}",
            )
        exercise_ids = (
            [block.exercise_id for block in day.training_session.blocks]
            if day.training_session is not None
            else []
        )
        stats_by_id = await self._exercises.list_target_stats_by_exercise(exercise_ids)
        diary_candidate_ids = (
            [day.training_session.id]
            if day.training_session is not None
            and day.session_type in self._DIARY_ELIGIBLE_SESSION_TYPES
            else []
        )
        diary_session_ids = await self._diary.list_session_ids_with_entries(diary_candidate_ids)
        return self._day_plan_to_read_schema(day, stats_by_id, diary_session_ids)
