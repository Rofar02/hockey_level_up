import { apiGet, apiPatchAuth } from './client'
import type { UserAdminRead, UserAdminUpdate } from '../types/user'

export interface ListUsersAdminFilters {
  q?: string
  limit?: number
  offset?: number
}

// GET /admin/users returns a bare array with no total-count field -- pages
// beyond the first are inferred by the caller from `result.length === limit`
// (see AdminUsersPage), same "no envelope" convention as /leaderboard.
export function listUsersAdmin(
  filters: ListUsersAdminFilters,
  accessToken: string,
): Promise<UserAdminRead[]> {
  const params = new URLSearchParams()
  if (filters.q !== undefined && filters.q !== '') {
    params.set('q', filters.q)
  }
  if (filters.limit !== undefined) {
    params.set('limit', String(filters.limit))
  }
  if (filters.offset !== undefined) {
    params.set('offset', String(filters.offset))
  }
  const query = params.toString()
  return apiGet<UserAdminRead[]>(`/admin/users${query !== '' ? `?${query}` : ''}`, accessToken)
}

export function updateUserAdmin(
  userId: string,
  payload: UserAdminUpdate,
  accessToken: string,
): Promise<UserAdminRead> {
  return apiPatchAuth<UserAdminRead>(`/admin/users/${userId}`, payload, accessToken)
}
