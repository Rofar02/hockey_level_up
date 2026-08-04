import { apiGet } from './client'
import type { SuggestedWeightRead } from '../types/setCompletion'

export function getSuggestedWeight(
  exerciseId: string,
  accessToken: string,
): Promise<SuggestedWeightRead> {
  return apiGet<SuggestedWeightRead>(`/exercises/${exerciseId}/suggested-weight`, accessToken)
}
