import uuid
from collections import defaultdict

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import (
    EQUIPMENT_REACH,
    EquipmentType,
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseTargetStat,
    MovementPattern,
    TargetStat,
    TrainingPhase,
)
from app.schemas.exercise import ExerciseCreate


class ExerciseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_exercises(
        self,
        category: ExerciseCategory | None = None,
        phase: TrainingPhase | None = None,
        equipment_type: EquipmentType | None = None,
        target_stat: TargetStat | None = None,
    ) -> list[Exercise]:
        query = select(Exercise)
        if category is not None:
            query = query.where(Exercise.category == category)
        if phase is not None:
            query = query.where(Exercise.phase == phase)
        if equipment_type is not None:
            query = query.where(Exercise.equipment_type == equipment_type)
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
        equipment_access: EquipmentType,
        category: ExerciseCategory | None = None,
        suitable_for_game_day: bool | None = None,
    ) -> list[Exercise]:
        """Candidates for training-session assembly.

        equipment_access only constrains off_ice exercises -- on the ice, the
        player doesn't choose gym/home/bodyweight, so on_ice exercises are
        never excluded by equipment. Off-ice uses cumulative reach (see
        EQUIPMENT_REACH), not an exact-tier match -- a gym member can still
        do a bodyweight-only or home-tier move, equipment_access is the
        ceiling of what they have, not the one tier they're confined to.
        Used to be an exact `equipment_type == equipment_access` match,
        which starved gym/home users of the (often easier) exercises tagged
        for a lower tier -- see suggest_party_exercises's docstring, which
        already used cumulative reach for its own, different reason
        (multi-member intersection) before this method caught up to it.

        suitable_for_game_day is None (no filter) for every regular on/off-ice
        session -- only ScheduleService._build_game_day_session's physical
        activation pick passes True, since a full warmup pool (e.g. loaded
        barbell work) isn't appropriate right before a game.
        """
        query = select(Exercise).where(Exercise.phase == phase)
        if category is not None:
            query = query.where(Exercise.category == category)
        if suitable_for_game_day is not None:
            query = query.where(Exercise.suitable_for_game_day == suitable_for_game_day)
        query = query.where(
            or_(
                Exercise.category == ExerciseCategory.ON_ICE,
                Exercise.equipment_type.in_(EQUIPMENT_REACH[equipment_access]),
            )
        )

        result = await self._session.execute(query.order_by(Exercise.name))
        return list(result.scalars().all())
