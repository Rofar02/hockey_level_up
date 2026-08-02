import { apiGet } from './client'
import type { TrainingBlockRead } from '../types/trainingBlock'

export function getCurrentTrainingBlock(accessToken: string): Promise<TrainingBlockRead> {
  return apiGet<TrainingBlockRead>('/training-block/current', accessToken)
}
