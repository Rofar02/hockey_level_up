import { apiDeleteAuth, apiGet, apiPostAuth } from './client'
import type {
  UserTemporaryRestrictionIn,
  UserTemporaryRestrictionRead,
} from '../types/userTemporaryRestriction'

export function listActiveRestrictions(accessToken: string): Promise<UserTemporaryRestrictionRead[]> {
  return apiGet<UserTemporaryRestrictionRead[]>('/users/me/restrictions', accessToken)
}

export function reportRestriction(
  body: UserTemporaryRestrictionIn,
  accessToken: string,
): Promise<UserTemporaryRestrictionRead> {
  return apiPostAuth<UserTemporaryRestrictionRead>('/users/me/restrictions', body, accessToken)
}

export function liftRestriction(restrictionId: string, accessToken: string): Promise<void> {
  return apiDeleteAuth<void>(`/users/me/restrictions/${restrictionId}`, accessToken)
}
