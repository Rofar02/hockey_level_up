import {
  apiDeleteAuthWithBody,
  apiGet,
  apiPatchAuth,
  apiPostAuth,
  apiPostMultipartAuth,
  apiPutAuth,
} from './client'
import type { EquipmentItem } from '../types/exercise'
import type {
  AvatarRingAccent,
  CoachPersonality,
  JerseyColor,
  ReminderPreference,
  SeasonPeriod,
  UserPublicRead,
  UserRead,
} from '../types/user'
import type { UserSkillPreference } from '../types/skill'

export interface UserProfileUpdate {
  last_name?: string
  first_name?: string
  patronymic?: string | null
  jersey_number?: number | null
  reminder_preference?: ReminderPreference
  season_period?: SeasonPeriod
  coach_personality?: CoachPersonality
  tournament_date?: string | null
  timezone?: string
  has_seen_weight_hint?: boolean
  has_gym_access?: boolean
  avatar_ring_accent?: AvatarRingAccent | null
  jersey_color?: JerseyColor | null
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

export function markCoachPersonalityIntroSeen(accessToken: string): Promise<UserRead> {
  return apiPostAuth<UserRead>('/users/me/coach-personality-intro-seen', {}, accessToken)
}

// Unlike markOnboardingTourSeen, this has no dedicated endpoint -- it's just
// one more simple field on the existing PATCH /users/me, same as changing
// reminder_preference or timezone from Settings.
export function markWeightHintSeen(accessToken: string): Promise<UserRead> {
  return updateProfile({ has_seen_weight_hint: true }, accessToken)
}

export function getSeenCoachmarks(accessToken: string): Promise<string[]> {
  return apiGet<string[]>('/users/me/coachmarks-seen', accessToken)
}

export function markCoachmarkSeen(hintId: string, accessToken: string): Promise<string[]> {
  return apiPostAuth<string[]>(`/users/me/coachmarks-seen/${encodeURIComponent(hintId)}`, {}, accessToken)
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

// 403s server-side unless userId is a friend or teammate of the caller --
// see UserService.get_public_profile.
export function getUserPublicProfile(userId: string, accessToken: string): Promise<UserPublicRead> {
  return apiGet<UserPublicRead>(`/users/${userId}/profile`, accessToken)
}

export function getMyEquipmentItems(accessToken: string): Promise<EquipmentItem[]> {
  return apiGet<EquipmentItem[]>('/users/me/equipment-items', accessToken)
}

export function replaceMyEquipmentItems(
  items: EquipmentItem[],
  accessToken: string,
): Promise<EquipmentItem[]> {
  return apiPutAuth<EquipmentItem[]>(
    '/users/me/equipment-items',
    { equipment_items: items },
    accessToken,
  )
}
