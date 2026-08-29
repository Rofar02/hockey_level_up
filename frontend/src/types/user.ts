export const POSITIONS = ['goalie', 'defense', 'forward'] as const
export type Position = (typeof POSITIONS)[number]

export const POSITION_LABELS: Record<Position, string> = {
  goalie: 'Вратарь',
  defense: 'Защитник',
  forward: 'Нападающий',
}

export const REMINDER_PREFERENCES = ['none', 'morning', 'evening'] as const
export type ReminderPreference = (typeof REMINDER_PREFERENCES)[number]

export const REMINDER_PREFERENCE_LABELS: Record<Exclude<ReminderPreference, 'none'>, string> = {
  morning: 'Утром в день тренировки',
  evening: 'Вечером накануне',
}

export const SEASON_PERIODS = ['offseason', 'preseason', 'season', 'playoffs'] as const
export type SeasonPeriod = (typeof SEASON_PERIODS)[number]

// No automatic detection (no access to the team's game schedule) -- the
// user picks their own period in settings. Only "season"/"playoffs"
// actually change training behavior server-side (lower off-ice volume,
// more frequent deload weeks, playoffs more so than season) -- offseason/
// preseason are stored but behaviorally inert for now.
export const SEASON_PERIOD_CHOICES: { value: SeasonPeriod; title: string; description: string }[] = [
  { value: 'offseason', title: 'Межсезонье', description: 'Общая физическая подготовка, восстановление' },
  { value: 'preseason', title: 'Предсезонье', description: 'Подготовка к старту сезона' },
  { value: 'season', title: 'Сезон', description: 'Регулярный сезон — тренировки чуть легче, разгрузки чаще' },
  { value: 'playoffs', title: 'Плей-офф', description: 'Финальная часть сезона — тренировки легче, разгрузки заметно чаще' },
]

// Level-gated cosmetics (item 6, 2026-08-30 gamification pass) -- see
// utils/levelUnlocks.ts for the level thresholds.
export const AVATAR_RING_ACCENTS = ['ice', 'persimmon', 'mix'] as const
export type AvatarRingAccent = (typeof AVATAR_RING_ACCENTS)[number]

export const AVATAR_RING_ACCENT_LABELS: Record<AvatarRingAccent, string> = {
  ice: 'Лёд',
  persimmon: 'Огонь',
  mix: 'Микс',
}

export const JERSEY_COLORS = ['white', 'ice', 'persimmon', 'gold'] as const
export type JerseyColor = (typeof JERSEY_COLORS)[number]

export const JERSEY_COLOR_LABELS: Record<JerseyColor, string> = {
  white: 'Белый',
  ice: 'Лёд',
  persimmon: 'Огонь',
  gold: 'Золото',
}

export const COACH_PERSONALITIES = ['calm', 'strict', 'humor', 'vibe'] as const
export type CoachPersonality = (typeof COACH_PERSONALITIES)[number]

// Purely templated (non-AI) tone for reminders -- see
// app/services/coach_personality_phrases.py. Deliberately not the same
// feature as CoachPage's real LLM "AI-тренер".
export const COACH_PERSONALITY_CHOICES: {
  value: CoachPersonality
  title: string
  description: string
}[] = [
  { value: 'calm', title: 'Спокойный', description: 'Ровный тон, по фактам, без эмоций' },
  { value: 'strict', title: 'Жёсткая дисциплина', description: 'Строго по делу, никаких поблажек' },
  { value: 'humor', title: 'С юмором', description: 'Жёсткий хоккейный юмор, подколки в раздевалочном стиле' },
  { value: 'vibe', title: 'Свой чел', description: 'Неформально, по-дружески, без напряга' },
]

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
  avatar_ring_accent: AvatarRingAccent | null
  jersey_color: JerseyColor | null
  // Only ever present on your own UserRead -- share it so a friend can send
  // you a request (see api/friends.ts). Never shown for anyone else (see
  // UserPublicRead below).
  friend_code: string | null
  // Stage 2.2: bypasses the equipment filter entirely when true. Owned
  // items themselves aren't part of this Read shape -- see
  // api/users.ts's listMyEquipmentItems/replaceMyEquipmentItems.
  has_gym_access: boolean
  email_verified: boolean
  is_admin: boolean
  has_premium: boolean
  xp: number
  level: number
  timezone: string
  reminder_preference: ReminderPreference
  season_period: SeasonPeriod
  coach_personality: CoachPersonality
  tournament_date: string | null
  has_seen_onboarding_tour: boolean
  has_seen_weight_hint: boolean
  created_at: string
}

// GET /users/{id}/profile -- what a friend or teammate can see, deliberately
// missing weight/height/email/everything-private that UserRead carries. 403
// if there's no friend/teammate relationship (see api/users.ts).
export interface UserPublicRead {
  id: string
  first_name: string
  last_name: string
  patronymic: string | null
  avatar_url: string | null
  avatar_ring_accent: AvatarRingAccent | null
  position: Position | null
  jersey_number: number | null
  jersey_color: JerseyColor | null
  years_of_experience: number | null
  level: number
  xp: number
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
