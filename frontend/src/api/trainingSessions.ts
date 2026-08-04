import { apiGet } from './client'
import type { ExerciseSetsRead } from '../types/setCompletion'

export function getExerciseSets(
  trainingSessionId: string,
  exerciseId: string,
  accessToken: string,
): Promise<ExerciseSetsRead> {
  return apiGet<ExerciseSetsRead>(
    `/training-sessions/${trainingSessionId}/exercises/${exerciseId}/sets`,
    accessToken,
  )
}
