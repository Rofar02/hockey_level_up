from pydantic import BaseModel

from app.models.schedule import BlockPhase


class TrainingBlockRead(BaseModel):
    block_number: int
    phase: BlockPhase
    # Session-count progress toward the next phase (Phase 4) -- e.g. 4/6.
    # Not meaningful for the deload->new-block rollover specifically (that
    # transition also respects the same threshold, just isn't a "next phase
    # within this block" the way accumulation->intensification is), but the
    # count/threshold pair is still accurate progress information either way.
    sessions_completed_in_phase: int
    sessions_to_advance: int
