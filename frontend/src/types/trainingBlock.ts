export const BLOCK_PHASES = ['accumulation', 'intensification', 'deload'] as const
export type BlockPhase = (typeof BLOCK_PHASES)[number]

export const BLOCK_PHASE_LABELS: Record<BlockPhase, string> = {
  accumulation: 'Накопление',
  intensification: 'Интенсификация',
  deload: 'Разгрузка',
}

export interface TrainingBlockRead {
  block_number: number
  phase: BlockPhase
  sessions_completed_in_phase: number
  sessions_to_advance: number
}
