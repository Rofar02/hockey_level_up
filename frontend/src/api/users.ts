import { apiGet, apiPatchAuth, apiPutAuth } from './client'
import type { EquipmentAccess, UserRead } from '../types/user'
import type { UserSkillPreference } from '../types/skill'

export function updateEquipmentAccess(
  equipmentAccess: EquipmentAccess,
  accessToken: string,
): Promise<UserRead> {
  return apiPatchAuth<UserRead>('/users/me', { equipment_access: equipmentAccess }, accessToken)
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
