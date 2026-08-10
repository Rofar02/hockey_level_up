import {
  apiDeleteAuthWithBody,
  apiGet,
  apiPatchAuth,
  apiPostAuth,
  apiPostMultipartAuth,
  apiPutAuth,
} from './client'
import type { EquipmentAccess, ReminderPreference, UserRead } from '../types/user'
import type { UserSkillPreference } from '../types/skill'

export function updateEquipmentAccess(
  equipmentAccess: EquipmentAccess,
  accessToken: string,
): Promise<UserRead> {
  return apiPatchAuth<UserRead>('/users/me', { equipment_access: equipmentAccess }, accessToken)
}

export interface UserProfileUpdate {
  last_name?: string
  first_name?: string
  patronymic?: string | null
  jersey_number?: number | null
  reminder_preference?: ReminderPreference
  timezone?: string
}

export function updateProfile(
  payload: UserProfileUpdate,
  accessToken: string,
): Promise<UserRead> {
  return apiPatchAuth<UserRead>('/users/me', payload, accessToken)
}

export function markOnboardingTourSeen(accessToken: string): Promise<UserRead> {
  return apiPostAuth<UserRead>('/users/me/onboarding-tour-seen', {}, accessToken)
}

export function uploadAvatar(file: File, accessToken: string): Promise<UserRead> {
  const formData = new FormData()
  formData.append('file', file)
  return apiPostMultipartAuth<UserRead>('/users/me/avatar', formData, accessToken)
}

export function getSkillPreferences(accessToken: string): Promise<UserSkillPreference[]> {
  return apiGet<UserSkillPreference[]>('/users/me/skill-preferences', accessToken)
}

export function replaceSkillPreferences(
  skillIds: string[],
  accessToken: string,
): Promise<UserSkillPreference[]> {
  return apiPutAuth<UserSkillPreference[]>(
    '/users/me/skill-preferences',
    { skill_ids: skillIds },
    accessToken,
  )
}

export function deleteAccount(password: string, accessToken: string): Promise<void> {
  return apiDeleteAuthWithBody<void>('/users/me', { password }, accessToken)
}
