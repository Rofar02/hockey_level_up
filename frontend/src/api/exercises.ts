import { apiDeleteAuth, apiGet, apiPatchAuth, apiPostAuth, apiPutAuth } from './client'
import type {
  ExerciseCategory,
  ExerciseRead,
  ExerciseWrite,
  MovementPattern,
  TargetStat,
} from '../types/exercise'
import type { TrainingPhase } from '../types/schedule'
import type { SuggestedWeightRead } from '../types/setCompletion'
import type { SkillTagRead } from '../types/skill'

export function getSuggestedWeight(
  exerciseId: string,
  accessToken: string,
): Promise<SuggestedWeightRead> {
  return apiGet<SuggestedWeightRead>(`/exercises/${exerciseId}/suggested-weight`, accessToken)
}

// -- admin CRUD --

export interface ExerciseFilters {
  category?: ExerciseCategory
  phase?: TrainingPhase
  target_stat?: TargetStat
}

export function listExercises(
  filters: ExerciseFilters,
  accessToken: string,
): Promise<ExerciseRead[]> {
  const params = new URLSearchParams()
  if (filters.category !== undefined) {
    params.set('category', filters.category)
  }
  if (filters.phase !== undefined) {
    params.set('phase', filters.phase)
  }
  if (filters.target_stat !== undefined) {
    params.set('target_stat', filters.target_stat)
  }
  const query = params.toString()
  return apiGet<ExerciseRead[]>(`/exercises${query !== '' ? `?${query}` : ''}`, accessToken)
}

export function createExercise(payload: ExerciseWrite, accessToken: string): Promise<ExerciseRead> {
  return apiPostAuth<ExerciseRead>('/exercises', payload, accessToken)
}

export function updateExercise(
  exerciseId: string,
  payload: ExerciseWrite,
  accessToken: string,
): Promise<ExerciseRead> {
  return apiPatchAuth<ExerciseRead>(`/exercises/${exerciseId}`, payload, accessToken)
}

export function deleteExercise(exerciseId: string, accessToken: string): Promise<void> {
  return apiDeleteAuth<void>(`/exercises/${exerciseId}`, accessToken)
}

export function listExerciseSkillTags(
  exerciseId: string,
  accessToken: string,
): Promise<SkillTagRead[]> {
  return apiGet<SkillTagRead[]>(`/exercises/${exerciseId}/skill-tags`, accessToken)
}

export function listExerciseMovementPatterns(
  exerciseId: string,
  accessToken: string,
): Promise<MovementPattern[]> {
  return apiGet<MovementPattern[]>(`/exercises/${exerciseId}/movement-patterns`, accessToken)
}

export function replaceExerciseMovementPatterns(
  exerciseId: string,
  patterns: MovementPattern[],
  accessToken: string,
): Promise<MovementPattern[]> {
  return apiPutAuth<MovementPattern[]>(
    `/exercises/${exerciseId}/movement-patterns`,
    { movement_patterns: patterns },
    accessToken,
  )
}
