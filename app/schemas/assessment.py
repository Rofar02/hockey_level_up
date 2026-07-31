from pydantic import BaseModel, ConfigDict, Field

from app.models.user import FitnessTier


class AssessmentTestIn(BaseModel):
    long_jump_cm: float = Field(gt=0)
    pushups_reps: float = Field(gt=0)
    squats_reps: float = Field(gt=0)
    plank_seconds: float = Field(gt=0)
    run_1km_seconds: float = Field(gt=0)


class AssessmentResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agility: float
    strength: float
    endurance: float
    intellect: float
    fitness_tier: FitnessTier


class AssessmentStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    has_assessment: bool
    suggested_reassessment: bool
