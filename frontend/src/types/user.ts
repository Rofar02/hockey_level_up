export const POSITIONS = ['goalie', 'defense', 'forward'] as const
export type Position = (typeof POSITIONS)[number]

export const POSITION_LABELS: Record<Position, string> = {
  goalie: 'Вратарь',
  defense: 'Защитник',
  forward: 'Нападающий',
}

export const EQUIPMENT_OPTIONS = ['gym', 'home', 'bodyweight'] as const
export type EquipmentAccess = (typeof EQUIPMENT_OPTIONS)[number]

// Shared between onboarding's equipment step and the settings screen so the
// copy for each card only has to be maintained in one place.
export const EQUIPMENT_CHOICES: { value: EquipmentAccess; title: string; description: string }[] = [
  { value: 'gym', title: 'Зал', description: 'Полный доступ к тренажёрам и свободным весам' },
  { value: 'home', title: 'Дом', description: 'Гантели, эспандеры и другой домашний инвентарь' },
  { value: 'bodyweight', title: 'Только тело', description: 'Тренировки без какого-либо инвентаря' },
]

export const REMINDER_PREFERENCES = ['none', 'morning', 'evening'] as const
export type ReminderPreference = (typeof REMINDER_PREFERENCES)[number]

export const REMINDER_PREFERENCE_LABELS: Record<Exclude<ReminderPreference, 'none'>, string> = {
  morning: 'Утром в день тренировки',
  evening: 'Вечером накануне',
}

export interface UserRead {
  id: string
  username: string
  email: string
  last_name: string
  first_name: string
  patronymic: string | null
  height: number | null
  weight: number | null
  age: number | null
  position: Position | null
  years_of_experience: number | null
  jersey_number: number | null
  avatar_url: string | null
  equipment_access: EquipmentAccess
  is_admin: boolean
  has_premium: boolean
  xp: number
  level: number
  timezone: string
  reminder_preference: ReminderPreference
  has_seen_onboarding_tour: boolean
  created_at: string
}

export interface UserAdminRead {
  id: string
  email: string
  first_name: string
  last_name: string
  level: number
  is_admin: boolean
  has_premium: boolean
  created_at: string
}

export interface UserAdminUpdate {
  is_admin?: boolean
  has_premium?: boolean
}

export interface RegisterPayload {
  email: string
  password: string
  last_name: string
  first_name: string
  jersey_number: number
  patronymic?: string | null
  height?: number | null
  weight?: number | null
  age?: number | null
  position?: Position | null
  years_of_experience?: number | null
  privacy_consent: boolean
}
