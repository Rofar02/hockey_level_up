import { apiGet } from './client'
import type { TrainingBlockRead } from '../types/trainingBlock'

// `optional=1`: no block yet (a new player) is null, not a 404 (15.10).
export const CURRENT_BLOCK_PATH = '/training-block/current?optional=1'

export function getCurrentTrainingBlock(accessToken: string): Promise<TrainingBlockRead | null> {
  return apiGet<TrainingBlockRead | null>(CURRENT_BLOCK_PATH, accessToken)
}
