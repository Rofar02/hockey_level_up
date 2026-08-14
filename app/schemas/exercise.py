import uuid

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.rest import rest_seconds_for
from app.models.exercise import (
    EquipmentType,
    Exercise,
    ExerciseCategory,
    ExerciseType,
    MovementPattern,
    MuscleGroup,
    StimulusType,
    TargetStat,
    TrainingPhase,
)


class ExerciseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    category: ExerciseCategory
    phase: TrainingPhase
    # Not a passthrough model attribute (Exercise has no target_stat column
    # or relationship() -- see ExerciseTargetStat) -- always supplied
    # explicitly by the service layer from a bulk ExerciseTargetStat query,
    # never auto-populated by from_attributes. Order matches ExerciseTargetStat.order;
    # index 0 is the "primary" stat ScheduleService buckets on for diversity.
    target_stats: list[TargetStat]
    difficulty_level: int = Field(ge=1, le=5)
    equipment_type: EquipmentType
    video_source_type: str | None
    video_source_id: str | None
    target_sets: int | None
    target_reps: int | None
    target_duration_seconds: int | None
    tracks_weight: bool
    bodyweight_ratio: float | None
    suitable_for_game_day: bool
    muscle_group: MuscleGroup | None
    stimulus_type: StimulusType | None
    exercise_type: ExerciseType | None

    # Computed, not stored -- see app.core.rest. Derived from target_reps
    # alone (None whenever target_sets/target_reps aren't both set), exposed
    # here so every client reads the same rest suggestion without
    # reimplementing the rep-range thresholds.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def rest_seconds(self) -> int | None:
        return rest_seconds_for(self.target_sets, self.target_reps)


# Every ExerciseRead must be built through here (or exercises_to_read for a
# batch), not ExerciseRead.model_validate(exercise) -- target_stats isn't a
# passthrough model attribute (see the field's docstring above), so
# from_attributes alone can't populate it. Callers fetch target_stats
# themselves (single via ExerciseRepository.list_target_stats, batch via
# list_target_stats_by_exercise) so this stays a pure function with no
# repository/session dependency of its own.
def exercise_to_read(exercise: Exercise, target_stats: list[TargetStat]) -> ExerciseRead:
    return ExerciseRead(
        id=exercise.id,
        name=exercise.name,
        description=exercise.description,
        category=exercise.category,
        phase=exercise.phase,
        target_stats=target_stats,
        difficulty_level=exercise.difficulty_level,
        equipment_type=exercise.equipment_type,
        video_source_type=exercise.video_source_type,
        video_source_id=exercise.video_source_id,
        target_sets=exercise.target_sets,
        target_reps=exercise.target_reps,
        target_duration_seconds=exercise.target_duration_seconds,
        tracks_weight=exercise.tracks_weight,
        bodyweight_ratio=exercise.bodyweight_ratio,
        suitable_for_game_day=exercise.suitable_for_game_day,
        muscle_group=exercise.muscle_group,
        stimulus_type=exercise.stimulus_type,
        exercise_type=exercise.exercise_type,
    )


def exercises_to_read(
    exercises: list[Exercise], target_stats_by_id: dict[uuid.UUID, list[TargetStat]]
) -> list[ExerciseRead]:
    return [exercise_to_read(e, target_stats_by_id.get(e.id, [])) for e in exercises]


class ExerciseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: ExerciseCategory
    phase: TrainingPhase
    difficulty_level: int = Field(ge=1, le=5)
    equipment_type: EquipmentType
    video_source_type: str | None = None
    video_source_id: str | None = None
    target_sets: int | None = None
    target_reps: int | None = None
    target_duration_seconds: int | None = None
    tracks_weight: bool = False
    bodyweight_ratio: float | None = Field(default=None, gt=0)
    suitable_for_game_day: bool = False
    muscle_group: MuscleGroup | None = None
    stimulus_type: StimulusType | None = None
    exercise_type: ExerciseType | None = None


class ExerciseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    category: ExerciseCategory | None = None
    phase: TrainingPhase | None = None
    difficulty_level: int | None = Field(default=None, ge=1, le=5)
    equipment_type: EquipmentType | None = None
    video_source_type: str | None = None
    video_source_id: str | None = None
    target_sets: int | None = None
    target_reps: int | None = None
    target_duration_seconds: int | None = None
    tracks_weight: bool | None = None
    bodyweight_ratio: float | None = Field(default=None, gt=0)
    suitable_for_game_day: bool | None = None
    muscle_group: MuscleGroup | None = None
    stimulus_type: StimulusType | None = None
    exercise_type: ExerciseType | None = None


class MovementPatternsReplace(BaseModel):
    movement_patterns: list[MovementPattern]


class TargetStatsReplace(BaseModel):
    # List order becomes ExerciseTargetStat.order on write -- index 0 is the
    # "primary" stat (see ExerciseRead.target_stats).
    target_stats: list[TargetStat]


class SuggestedWeightRead(BaseModel):
    # None whenever a suggestion can't be computed: the exercise doesn't
    # track weight, the user hasn't set a body weight, or bodyweight_ratio
    # isn't configured for this exercise yet -- see WeightSuggestionService.
    suggested_weight_kg: float | None
