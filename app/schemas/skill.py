import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.exercise import TargetStat


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class SkillStatWeightRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    skill_id: uuid.UUID
    stat_type: TargetStat
    weight: float = Field(ge=0.0, le=1.0)


class SkillStatWeightCreate(BaseModel):
    stat_type: TargetStat
    weight: float = Field(ge=0.0, le=1.0)


class SkillStatWeightUpdate(BaseModel):
    stat_type: TargetStat | None = None
    weight: float | None = Field(default=None, ge=0.0, le=1.0)


class SkillTagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    skill_id: uuid.UUID
    exercise_id: uuid.UUID
    transfer_note: str


class SkillTagCreate(BaseModel):
    exercise_id: uuid.UUID
    transfer_note: str = Field(min_length=1)


class SkillTagUpdate(BaseModel):
    transfer_note: str | None = Field(default=None, min_length=1)


class SkillMilestoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    skill_id: uuid.UUID
    threshold: int = Field(ge=0, le=100)
    title: str
    description: str


class SkillMilestoneCreate(BaseModel):
    threshold: int = Field(ge=0, le=100)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)


class SkillMilestoneUpdate(BaseModel):
    threshold: int | None = Field(default=None, ge=0, le=100)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)


class NextMilestoneRead(BaseModel):
    title: str
    threshold: int
    points_remaining: float


class SkillSummaryRead(BaseModel):
    id: uuid.UUID
    name: str
    value: float
    next_milestone: NextMilestoneRead | None


class StatContributionRead(BaseModel):
    stat_type: TargetStat
    weight: float
    effective_value: float
    contribution: float


class SkillMilestoneStatusRead(BaseModel):
    id: uuid.UUID
    threshold: int
    title: str
    description: str
    achieved: bool


class SkillDetailRead(BaseModel):
    id: uuid.UUID
    name: str
    value: float
    stat_breakdown: list[StatContributionRead]
    milestones: list[SkillMilestoneStatusRead]
