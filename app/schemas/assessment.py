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


class OnIceAssessmentTestIn(BaseModel):
    on_ice_skating_seconds: float = Field(gt=0)
    puck_handling_seconds: float = Field(gt=0)


class OnIceAssessmentResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    on_ice_skating: float
    puck_handling: float


class OnIceAssessmentStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    has_onice_assessment: bool
    suggested_onice_reassessment: bool
