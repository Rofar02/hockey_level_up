import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.exercise import EquipmentType, ExerciseCategory, TargetStat, TrainingPhase


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


class SuggestedWeightRead(BaseModel):
    # None whenever a suggestion can't be computed: the exercise doesn't
    # track weight, the user hasn't set a body weight, or bodyweight_ratio
    # isn't configured for this exercise yet -- see WeightSuggestionService.
    suggested_weight_kg: float | None
