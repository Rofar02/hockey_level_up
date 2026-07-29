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
