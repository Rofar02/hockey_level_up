import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import (
    EquipmentItem,
    Exercise,
    ExerciseCategory,
    MovementPattern,
    MuscleGroup,
    TargetStat,
    TrainingPhase,
)
from app.repositories.exercise_repository import ExerciseRepository
from app.schemas.exercise import (
    CatalogHealthIssue,
    ExerciseCreate,
    ExerciseEquipmentRequirement,
    ExerciseRead,
    ExerciseUpdate,
    MuscleGroupWeight,
    exercise_to_read,
    exercises_to_read,
)

# Same tolerance/precedent as skill_service.WEIGHT_SUM_EPSILON -- duplicated
# rather than imported cross-service, this codebase's established
# convention for small stable constants (see e.g. the frontend's own copy
# in AdminSkillDetailPage.tsx).
WEIGHT_SUM_EPSILON = 1e-6


class ExerciseService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._exercises = ExerciseRepository(session)

    async def list_exercises(
        self,
        category: ExerciseCategory | None = None,
        phase: TrainingPhase | None = None,
        target_stat: TargetStat | None = None,
    ) -> list[ExerciseRead]:
        exercises = await self._exercises.list_exercises(
            category=category,
            phase=phase,
            target_stat=target_stat,
        )
        stats_by_id = await self._exercises.list_target_stats_by_exercise(
            [exercise.id for exercise in exercises]
        )
        return exercises_to_read(exercises, stats_by_id)

    async def get_exercise(self, exercise_id: uuid.UUID) -> Exercise:
        exercise = await self._exercises.get_by_id(exercise_id)
        if exercise is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found"
            )
        return exercise

    async def get_exercise_read(self, exercise_id: uuid.UUID) -> ExerciseRead:
        exercise = await self.get_exercise(exercise_id)
        target_stats = await self._exercises.list_target_stats(exercise_id)
        return exercise_to_read(exercise, target_stats)

    async def create_exercise(self, data: ExerciseCreate) -> ExerciseRead:
        try:
            exercise = await self._exercises.create(data)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Exercise name already exists"
            ) from exc
        # Freshly created -- no target_stats yet, set via the dedicated
        # PUT .../target-stats afterwards (same two-step flow as
        # movement_patterns/skill-tags: the exercise must exist first).
        return exercise_to_read(exercise, [])

    async def update_exercise(self, exercise_id: uuid.UUID, data: ExerciseUpdate) -> ExerciseRead:
        exercise = await self.get_exercise(exercise_id)

        updates = data.model_dump(exclude_unset=True)
        try:
            await self._exercises.update(exercise, updates)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Exercise name already exists"
            ) from exc
        await self._session.refresh(exercise)
        target_stats = await self._exercises.list_target_stats(exercise_id)
        return exercise_to_read(exercise, target_stats)

    async def list_target_stats(self, exercise_id: uuid.UUID) -> list[TargetStat]:
        await self.get_exercise(exercise_id)
        return await self._exercises.list_target_stats(exercise_id)

    async def replace_target_stats(
        self, exercise_id: uuid.UUID, stats: list[TargetStat]
    ) -> list[TargetStat]:
        await self.get_exercise(exercise_id)
        unique_stats = list(dict.fromkeys(stats))
        await self._exercises.replace_target_stats(exercise_id, unique_stats)
        await self._session.commit()
        return unique_stats

    async def list_movement_patterns(self, exercise_id: uuid.UUID) -> list[MovementPattern]:
        await self.get_exercise(exercise_id)
        return await self._exercises.list_movement_patterns(exercise_id)

    async def replace_movement_patterns(
        self, exercise_id: uuid.UUID, patterns: list[MovementPattern]
    ) -> list[MovementPattern]:
        await self.get_exercise(exercise_id)
        unique_patterns = list(dict.fromkeys(patterns))
        await self._exercises.replace_movement_patterns(exercise_id, unique_patterns)
        await self._session.commit()
        return unique_patterns

    async def list_muscle_groups(self, exercise_id: uuid.UUID) -> list[MuscleGroupWeight]:
        await self.get_exercise(exercise_id)
        rows = await self._exercises.list_muscle_groups(exercise_id)
        return [MuscleGroupWeight(muscle_group=r.muscle_group, weight=r.weight) for r in rows]

    async def replace_muscle_groups(
        self, exercise_id: uuid.UUID, groups: list[MuscleGroupWeight]
    ) -> list[MuscleGroupWeight]:
        await self.get_exercise(exercise_id)
        # dict, not list -- also de-duplicates a repeated muscle_group the
        # same way replace_movement_patterns' dict.fromkeys does, last value
        # for a given group wins.
        weights: dict[MuscleGroup, float] = {g.muscle_group: g.weight for g in groups}
        total = sum(weights.values())
        if total > 1.0 + WEIGHT_SUM_EPSILON:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"sum of muscle group weights would exceed 1.0: got {round(total, 6)}",
            )
        await self._exercises.replace_muscle_groups(exercise_id, weights)
        await self._session.commit()
        return [MuscleGroupWeight(muscle_group=g, weight=w) for g, w in weights.items()]

    async def list_equipment_requirements(self) -> list[ExerciseEquipmentRequirement]:
        exercises = await self._exercises.list_exercises(category=ExerciseCategory.OFF_ICE)
        by_exercise = await self._exercises.list_equipment_items_by_exercise(
            [exercise.id for exercise in exercises]
        )
        return [
            ExerciseEquipmentRequirement(
                exercise_id=exercise.id, equipment_items=sorted(by_exercise.get(exercise.id, set()))
            )
            for exercise in exercises
        ]

    async def list_catalog_health_issues(self) -> list[CatalogHealthIssue]:
        """Stage 3 (2026-08-20 planning session) -- see CatalogHealthIssue's
        own docstring for exactly what each `missing` value means and why.
        Three bulk lookups plus one Python pass, same "fetch once, compute
        in Python" shape as ScheduleService._pick_main -- no per-exercise
        query, so this stays cheap even as the catalog grows.
        """
        exercises = await self._exercises.list_exercises()
        exercise_ids = [exercise.id for exercise in exercises]
        primary_stats = await self._exercises.list_primary_target_stats(exercise_ids)
        patterns_by_exercise = await self._exercises.list_movement_patterns_by_exercise(exercise_ids)
        equipment_by_exercise = await self._exercises.list_equipment_items_by_exercise(exercise_ids)

        issues: list[CatalogHealthIssue] = []
        for exercise in exercises:
            missing: list[str] = []
            if (
                exercise.category == ExerciseCategory.OFF_ICE
                and exercise.id not in primary_stats
            ):
                missing.append("primary_target_stat")
            if not patterns_by_exercise.get(exercise.id):
                missing.append("movement_pattern")
            if exercise.phase == TrainingPhase.WARMUP and exercise.warmup_stage is None:
                missing.append("warmup_stage")
            if (
                exercise.category == ExerciseCategory.OFF_ICE
                and exercise.tracks_weight
                and not equipment_by_exercise.get(exercise.id)
            ):
                missing.append("equipment_for_tracked_weight")

            if missing:
                issues.append(
                    CatalogHealthIssue(
                        exercise_id=exercise.id,
                        name=exercise.name,
                        category=exercise.category,
                        phase=exercise.phase,
                        missing=missing,
                    )
                )
        return issues

    async def list_equipment_items(self, exercise_id: uuid.UUID) -> list[EquipmentItem]:
        await self.get_exercise(exercise_id)
        return await self._exercises.list_equipment_items(exercise_id)

    async def replace_equipment_items(
        self, exercise_id: uuid.UUID, items: list[EquipmentItem]
    ) -> list[EquipmentItem]:
        await self.get_exercise(exercise_id)
        unique_items = list(dict.fromkeys(items))
        await self._exercises.replace_equipment_items(exercise_id, unique_items)
        await self._session.commit()
        return unique_items

    async def delete_exercise(self, exercise_id: uuid.UUID) -> None:
        exercise = await self.get_exercise(exercise_id)
        try:
            await self._exercises.delete(exercise)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Exercise is used in existing training sessions and cannot be deleted",
            ) from exc
