import { apiDeleteAuth, apiGet, apiPatchAuth, apiPostAuth, apiPutAuth } from './client'
import type {
  EquipmentItem,
  ExerciseCategory,
  ExerciseEquipmentRequirement,
  ExerciseRead,
  ExerciseWrite,
  MovementPattern,
  MuscleGroupWeight,
  TargetStat,
} from '../types/exercise'
import type { TrainingPhase } from '../types/schedule'
import type { SuggestedRepsRead, SuggestedWeightRead } from '../types/setCompletion'
import type { SkillTagRead } from '../types/skill'

export function getSuggestedWeight(
  exerciseId: string,
  accessToken: string,
): Promise<SuggestedWeightRead> {
  return apiGet<SuggestedWeightRead>(`/exercises/${exerciseId}/suggested-weight`, accessToken)
}

export function getSuggestedReps(
  exerciseId: string,
  accessToken: string,
): Promise<SuggestedRepsRead> {
  return apiGet<SuggestedRepsRead>(`/exercises/${exerciseId}/suggested-reps`, accessToken)
}

export function listExerciseEquipmentRequirements(
  accessToken: string,
): Promise<ExerciseEquipmentRequirement[]> {
  return apiGet<ExerciseEquipmentRequirement[]>('/exercises/equipment-requirements', accessToken)
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

export function listExerciseMuscleGroups(
  exerciseId: string,
  accessToken: string,
): Promise<MuscleGroupWeight[]> {
  return apiGet<MuscleGroupWeight[]>(`/exercises/${exerciseId}/muscle-groups`, accessToken)
}

export function replaceExerciseMuscleGroups(
  exerciseId: string,
  groups: MuscleGroupWeight[],
  accessToken: string,
): Promise<MuscleGroupWeight[]> {
  return apiPutAuth<MuscleGroupWeight[]>(
    `/exercises/${exerciseId}/muscle-groups`,
    { muscle_groups: groups },
    accessToken,
  )
}

export function listExerciseEquipmentItems(
  exerciseId: string,
  accessToken: string,
): Promise<EquipmentItem[]> {
  return apiGet<EquipmentItem[]>(`/exercises/${exerciseId}/equipment-items`, accessToken)
}

export function replaceExerciseEquipmentItems(
  exerciseId: string,
  items: EquipmentItem[],
  accessToken: string,
): Promise<EquipmentItem[]> {
  return apiPutAuth<EquipmentItem[]>(
    `/exercises/${exerciseId}/equipment-items`,
    { equipment_items: items },
    accessToken,
  )
}

export function listExerciseTargetStats(
  exerciseId: string,
  accessToken: string,
): Promise<TargetStat[]> {
  return apiGet<TargetStat[]>(`/exercises/${exerciseId}/target-stats`, accessToken)
}

// List order becomes ExerciseTargetStat.order server-side -- index 0 is the
// "primary" stat (see ExerciseRead.target_stats).
export function replaceExerciseTargetStats(
  exerciseId: string,
  stats: TargetStat[],
  accessToken: string,
): Promise<TargetStat[]> {
  return apiPutAuth<TargetStat[]>(
    `/exercises/${exerciseId}/target-stats`,
    { target_stats: stats },
    accessToken,
  )
}
