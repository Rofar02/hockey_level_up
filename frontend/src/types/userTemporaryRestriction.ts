import type { MovementPattern, MuscleGroup } from './exercise'

// Exactly one of the two, never both -- mirrors the backend CHECK
// constraint on UserTemporaryRestriction (2026-08-27: added muscle_group
// alongside the original movement_pattern for RestrictionsPage's
// body-avatar picker).
export interface UserTemporaryRestrictionIn {
  movement_pattern: MovementPattern | null
  muscle_group: MuscleGroup | null
  reason: string | null
}

export interface UserTemporaryRestrictionRead {
  id: string
  movement_pattern: MovementPattern | null
  muscle_group: MuscleGroup | null
  reason: string | null
  created_at: string
  expires_at: string
  lifted_at: string | null
}
