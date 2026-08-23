import type { MovementPattern } from './exercise'

export interface UserTemporaryRestrictionIn {
  movement_pattern: MovementPattern
  reason: string | null
}

export interface UserTemporaryRestrictionRead {
  id: string
  movement_pattern: MovementPattern
  reason: string | null
  created_at: string
  expires_at: string
  lifted_at: string | null
}
