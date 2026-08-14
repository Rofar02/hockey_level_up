import uuid

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.rest import rest_seconds_for
from app.models.exercise import (
    EquipmentType,
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
    target_stat: TargetStat
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


class ExerciseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: ExerciseCategory
    phase: TrainingPhase
    target_stat: TargetStat
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
    target_stat: TargetStat | None = None
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


class SuggestedWeightRead(BaseModel):
    # None whenever a suggestion can't be computed: the exercise doesn't
    # track weight, the user hasn't set a body weight, or bodyweight_ratio
    # isn't configured for this exercise yet -- see WeightSuggestionService.
    suggested_weight_kg: float | None
