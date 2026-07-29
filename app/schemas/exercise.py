import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.exercise import EquipmentType, ExerciseCategory, TargetStat, TrainingPhase


class ExerciseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: ExerciseCategory
    phase: TrainingPhase
    target_stat: TargetStat
    difficulty_level: int = Field(ge=1, le=5)
    equipment_type: EquipmentType
    video_source_type: str | None
    video_source_id: str | None
