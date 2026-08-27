import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import (
    EquipmentItem,
    Exercise,
    ExerciseCategory,
    ExerciseEquipmentItem,
    ExerciseMovementPattern,
    ExerciseMuscleGroup,
    ExerciseTargetStat,
    GYM_COVERED_ITEMS,
    MovementPattern,
    MuscleGroup,
    TargetStat,
    TrainingPhase,
    UserEquipmentItem,
)
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.schemas.exercise import ExerciseCreate


class ExerciseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_exercises(
        self,
        category: ExerciseCategory | None = None,
        phase: TrainingPhase | None = None,
        target_stat: TargetStat | None = None,
    ) -> list[Exercise]:
        query = select(Exercise)
        if category is not None:
            query = query.where(Exercise.category == category)
        if phase is not None:
            query = query.where(Exercise.phase == phase)
        if target_stat is not None:
            # "Has this stat anywhere among its target_stats", not just the
            # primary (order=0) one -- this is an admin browsing/filtering
            # convenience, not the diversity-selection mechanism in
            # ScheduleService, so there's no notion of "primary" here.
            query = query.where(
                select(ExerciseTargetStat.id)
                .where(
                    ExerciseTargetStat.exercise_id == Exercise.id,
                    ExerciseTargetStat.target_stat == target_stat,
                )
                .exists()
            )

        result = await self._session.execute(query.order_by(Exercise.name))
        return list(result.scalars().all())

    async def list_target_stats(self, exercise_id: uuid.UUID) -> list[TargetStat]:
        result = await self._session.execute(
            select(ExerciseTargetStat.target_stat)
            .where(ExerciseTargetStat.exercise_id == exercise_id)
            .order_by(ExerciseTargetStat.order)
        )
        return list(result.scalars().all())

    async def list_target_stats_by_exercise(
        self, exercise_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[TargetStat]]:
        """Bulk read-side lookup, ordered per exercise -- for enriching
        ExerciseRead.target_stats without an N+1 query per exercise."""
        if not exercise_ids:
            return {}
        result = await self._session.execute(
            select(ExerciseTargetStat.exercise_id, ExerciseTargetStat.target_stat)
            .where(ExerciseTargetStat.exercise_id.in_(exercise_ids))
            .order_by(ExerciseTargetStat.exercise_id, ExerciseTargetStat.order)
        )
        by_exercise: dict[uuid.UUID, list[TargetStat]] = defaultdict(list)
        for exercise_id, target_stat in result.all():
            by_exercise[exercise_id].append(target_stat)
        return dict(by_exercise)

    async def list_primary_target_stats(
        self, exercise_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, TargetStat]:
        """Bulk order=0 lookup -- the diversity-bucketing key for
        ScheduleService._pick_main/suggest_party_exercises. An exercise with
        no target_stats at all (e.g. just created, not yet tagged via
        PUT .../target-stats) is simply absent from the result."""
        if not exercise_ids:
            return {}
        result = await self._session.execute(
            select(ExerciseTargetStat.exercise_id, ExerciseTargetStat.target_stat).where(
                ExerciseTargetStat.exercise_id.in_(exercise_ids), ExerciseTargetStat.order == 0
            )
        )
        return dict(result.all())

    async def list_exercise_ids_with_stat(
        self, exercise_ids: list[uuid.UUID], stat: TargetStat
    ) -> set[uuid.UUID]:
        """Which of exercise_ids have `stat` anywhere among their
        target_stats (not necessarily primary) -- mirrors
        SkillRepository.list_tagged_exercise_ids's shape."""
        if not exercise_ids:
            return set()
        result = await self._session.execute(
            select(ExerciseTargetStat.exercise_id).where(
                ExerciseTargetStat.exercise_id.in_(exercise_ids), ExerciseTargetStat.target_stat == stat
            )
        )
        return set(result.scalars().all())

    async def replace_target_stats(self, exercise_id: uuid.UUID, stats: list[TargetStat]) -> None:
        await self._session.execute(
            delete(ExerciseTargetStat).where(ExerciseTargetStat.exercise_id == exercise_id)
        )
        for order, stat in enumerate(stats):
            self._session.add(
                ExerciseTargetStat(exercise_id=exercise_id, target_stat=stat, order=order)
            )
        await self._session.flush()

    async def list_movement_patterns(self, exercise_id: uuid.UUID) -> list[MovementPattern]:
        result = await self._session.execute(
            select(ExerciseMovementPattern.movement_pattern).where(
                ExerciseMovementPattern.exercise_id == exercise_id
            )
        )
        return list(result.scalars().all())

    async def list_movement_patterns_by_exercise(
        self, exercise_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[MovementPattern]]:
        """Bulk lookup for ScheduleService's warmup/cooldown-to-main matching
        (Phase 3) -- mirrors list_target_stats_by_exercise's shape. An
        exercise with no movement_pattern rows is simply absent from the
        result, same as an exercise with no target_stats."""
        if not exercise_ids:
            return {}
        result = await self._session.execute(
            select(ExerciseMovementPattern.exercise_id, ExerciseMovementPattern.movement_pattern).where(
                ExerciseMovementPattern.exercise_id.in_(exercise_ids)
            )
        )
        by_exercise: dict[uuid.UUID, list[MovementPattern]] = defaultdict(list)
        for exercise_id, pattern in result.all():
            by_exercise[exercise_id].append(pattern)
        return dict(by_exercise)

    async def replace_movement_patterns(
        self, exercise_id: uuid.UUID, patterns: list[MovementPattern]
    ) -> None:
        await self._session.execute(
            delete(ExerciseMovementPattern).where(ExerciseMovementPattern.exercise_id == exercise_id)
        )
        for pattern in patterns:
            self._session.add(
                ExerciseMovementPattern(exercise_id=exercise_id, movement_pattern=pattern)
            )
        await self._session.flush()

    async def list_muscle_groups(self, exercise_id: uuid.UUID) -> list[ExerciseMuscleGroup]:
        result = await self._session.execute(
            select(ExerciseMuscleGroup).where(ExerciseMuscleGroup.exercise_id == exercise_id)
        )
        return list(result.scalars().all())

    async def list_muscle_groups_by_exercise(
        self, exercise_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, set[MuscleGroup]]:
        """Bulk lookup for ScheduleService._apply_muscle_balance -- mirrors
        list_movement_patterns_by_exercise's shape. A set, not a list: the
        balance rule only ever checks presence (see ExerciseMuscleGroup's
        docstring), never the weight value."""
        if not exercise_ids:
            return {}
        result = await self._session.execute(
            select(ExerciseMuscleGroup.exercise_id, ExerciseMuscleGroup.muscle_group).where(
                ExerciseMuscleGroup.exercise_id.in_(exercise_ids)
            )
        )
        by_exercise: dict[uuid.UUID, set[MuscleGroup]] = defaultdict(set)
        for exercise_id, group in result.all():
            by_exercise[exercise_id].add(group)
        return dict(by_exercise)

    async def replace_muscle_groups(
        self, exercise_id: uuid.UUID, weights: dict[MuscleGroup, float]
    ) -> None:
        await self._session.execute(
            delete(ExerciseMuscleGroup).where(ExerciseMuscleGroup.exercise_id == exercise_id)
        )
        for group, weight in weights.items():
            self._session.add(
                ExerciseMuscleGroup(exercise_id=exercise_id, muscle_group=group, weight=weight)
            )
        await self._session.flush()

    async def list_equipment_items(self, exercise_id: uuid.UUID) -> list[EquipmentItem]:
        result = await self._session.execute(
            select(ExerciseEquipmentItem.equipment_item).where(
                ExerciseEquipmentItem.exercise_id == exercise_id
            )
        )
        return list(result.scalars().all())

    async def list_equipment_items_by_exercise(
        self, exercise_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, set[EquipmentItem]]:
        """Bulk lookup for ScheduleService.suggest_party_exercises' own
        per-member subset check -- mirrors list_muscle_groups_by_exercise's
        shape."""
        if not exercise_ids:
            return {}
        result = await self._session.execute(
            select(ExerciseEquipmentItem.exercise_id, ExerciseEquipmentItem.equipment_item).where(
                ExerciseEquipmentItem.exercise_id.in_(exercise_ids)
            )
        )
        by_exercise: dict[uuid.UUID, set[EquipmentItem]] = defaultdict(set)
        for exercise_id, item in result.all():
            by_exercise[exercise_id].add(item)
        return dict(by_exercise)

    async def replace_equipment_items(
        self, exercise_id: uuid.UUID, items: list[EquipmentItem]
    ) -> None:
        await self._session.execute(
            delete(ExerciseEquipmentItem).where(ExerciseEquipmentItem.exercise_id == exercise_id)
        )
        for item in items:
            self._session.add(
                ExerciseEquipmentItem(exercise_id=exercise_id, equipment_item=item)
            )
        await self._session.flush()

    async def list_owned_equipment(self, user_id: uuid.UUID) -> set[EquipmentItem]:
        result = await self._session.execute(
            select(UserEquipmentItem.equipment_item).where(UserEquipmentItem.user_id == user_id)
        )
        return set(result.scalars().all())

    async def list_active_restricted_patterns(self, user_id: uuid.UUID) -> set[MovementPattern]:
        """Same self-contained, keyed-off-user shape as list_owned_equipment
        above -- called internally by list_for_assembly, not threaded in as
        a parameter from every caller. "Active" mirrors
        UserTemporaryRestrictionRepository's own definition (expires_at >=
        today, not lifted) -- duplicated here rather than importing that
        repository, same deliberate duplication convention already used
        elsewhere in this codebase (see streak_service.TRAINING_SESSION_TYPES
        vs. training_block_repository._TRAINING_SESSION_TYPES)."""
        result = await self._session.execute(
            select(UserTemporaryRestriction.movement_pattern).where(
                UserTemporaryRestriction.user_id == user_id,
                UserTemporaryRestriction.movement_pattern.is_not(None),
                UserTemporaryRestriction.expires_at >= date.today(),
                UserTemporaryRestriction.lifted_at.is_(None),
            )
        )
        return set(result.scalars().all())

    # Mirrors list_active_restricted_patterns exactly, muscle_group instead
    # of movement_pattern -- the body-avatar picker's report path (see
    # UserTemporaryRestriction's own docstring for why a restriction is one
    # or the other, never both).
    async def list_active_restricted_muscle_groups(self, user_id: uuid.UUID) -> set[MuscleGroup]:
        result = await self._session.execute(
            select(UserTemporaryRestriction.muscle_group).where(
                UserTemporaryRestriction.user_id == user_id,
                UserTemporaryRestriction.muscle_group.is_not(None),
                UserTemporaryRestriction.expires_at >= date.today(),
                UserTemporaryRestriction.lifted_at.is_(None),
            )
        )
        return set(result.scalars().all())

    async def list_owned_equipment_by_user(
        self, user_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, set[EquipmentItem]]:
        """Bulk lookup for ScheduleService.suggest_party_exercises, which
        needs every member's owned set at once to intersect eligibility
        across the party -- mirrors list_muscle_groups_by_exercise's shape."""
        if not user_ids:
            return {}
        result = await self._session.execute(
            select(UserEquipmentItem.user_id, UserEquipmentItem.equipment_item).where(
                UserEquipmentItem.user_id.in_(user_ids)
            )
        )
        by_user: dict[uuid.UUID, set[EquipmentItem]] = defaultdict(set)
        for user_id, item in result.all():
            by_user[user_id].add(item)
        return dict(by_user)

    async def replace_owned_equipment(self, user_id: uuid.UUID, items: list[EquipmentItem]) -> None:
        await self._session.execute(
            delete(UserEquipmentItem).where(UserEquipmentItem.user_id == user_id)
        )
        for item in items:
            self._session.add(UserEquipmentItem(user_id=user_id, equipment_item=item))
        await self._session.flush()

    async def get_by_id(self, exercise_id: uuid.UUID) -> Exercise | None:
        return await self._session.get(Exercise, exercise_id)

    async def create(self, data: ExerciseCreate) -> Exercise:
        exercise = Exercise(**data.model_dump())
        self._session.add(exercise)
        await self._session.flush()
        return exercise

    async def update(self, exercise: Exercise, updates: dict) -> Exercise:
        for field, value in updates.items():
            setattr(exercise, field, value)
        await self._session.flush()
        return exercise

    async def delete(self, exercise: Exercise) -> None:
        await self._session.delete(exercise)
        await self._session.flush()

    async def list_for_assembly(
        self,
        phase: TrainingPhase,
        user: User,
        category: ExerciseCategory | None = None,
        suitable_for_game_day: bool | None = None,
    ) -> list[Exercise]:
        """Candidates for training-session assembly.

        Equipment only constrains off_ice exercises -- on the ice, the
        player doesn't choose their gear, so on_ice exercises are never
        excluded by it. Off-ice (Stage 2.2, 2026-08-20 planning session;
        personal-gear split 2026-08-22): user.has_gym_access=True bypasses
        the filter for every item in GYM_COVERED_ITEMS (sees every exercise
        that only requires those, including future new gym items with no
        changes needed here) but NOT for PERSONAL_GEAR_ITEMS (e.g. a hockey
        stick) -- those always require an explicit UserEquipmentItem row
        regardless of gym access, since a commercial gym doesn't stock
        them. An exercise is eligible only if *every* item it requires is
        covered -- either gym-bypassed or explicitly owned (subset check,
        expressed below as "no required row outside the covered set
        exists") -- a step-up tagged with both step platform and dumbbells
        needs both covered, one isn't enough. An exercise with zero
        required rows (plain bodyweight work) is always eligible,
        regardless of inventory or gym access.

        suitable_for_game_day is None (no filter) for every regular on/off-ice
        session -- only ScheduleService._build_game_day_session's physical
        activation pick passes True, since a full warmup pool (e.g. loaded
        barbell work) isn't appropriate right before a game.

        UserTemporaryRestriction (P3 item #7, extended 2026-08-27 with
        muscle_group): unlike the equipment filter above, this excludes an
        exercise for EVERY category, ON_ICE included -- a restricted
        movement/muscle is restricted regardless of where the exercise
        happens. Whole-exercise exclusion, not per-pattern: an exercise
        tagged with both a restricted pattern (or muscle group) and an
        unrestricted one is still fully excluded, the same binary
        "eligible or not" shape the equipment check above already uses. A
        muscle_group restriction is checked against ExerciseMuscleGroup by
        presence only, same "is this group tagged at all" contract
        ScheduleService._apply_muscle_balance already uses -- not the
        weight, which exists for that balancer's finer-grained use, not
        this binary exclusion.
        """
        query = select(Exercise).where(Exercise.phase == phase)
        if category is not None:
            query = query.where(Exercise.category == category)
        if suitable_for_game_day is not None:
            query = query.where(Exercise.suitable_for_game_day == suitable_for_game_day)

        owned = await self.list_owned_equipment(user.id)
        covered = owned | GYM_COVERED_ITEMS if user.has_gym_access else owned
        missing_required_item = (
            select(ExerciseEquipmentItem.id)
            .where(
                ExerciseEquipmentItem.exercise_id == Exercise.id,
                ExerciseEquipmentItem.equipment_item.notin_(covered),
            )
            .exists()
        )
        query = query.where(
            or_(
                Exercise.category == ExerciseCategory.ON_ICE,
                ~missing_required_item,
            )
        )

        restricted_patterns = await self.list_active_restricted_patterns(user.id)
        if restricted_patterns:
            has_restricted_pattern = (
                select(ExerciseMovementPattern.id)
                .where(
                    ExerciseMovementPattern.exercise_id == Exercise.id,
                    ExerciseMovementPattern.movement_pattern.in_(restricted_patterns),
                )
                .exists()
            )
            query = query.where(~has_restricted_pattern)

        restricted_muscle_groups = await self.list_active_restricted_muscle_groups(user.id)
        if restricted_muscle_groups:
            has_restricted_muscle_group = (
                select(ExerciseMuscleGroup.id)
                .where(
                    ExerciseMuscleGroup.exercise_id == Exercise.id,
                    ExerciseMuscleGroup.muscle_group.in_(restricted_muscle_groups),
                )
                .exists()
            )
            query = query.where(~has_restricted_muscle_group)

        result = await self._session.execute(query.order_by(Exercise.name))
        return list(result.scalars().all())
