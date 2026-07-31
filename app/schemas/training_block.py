from pydantic import BaseModel

from app.core.training_block import BlockPhase


class TrainingBlockRead(BaseModel):
    block_number: int
    week_in_block: int
    phase: BlockPhase
