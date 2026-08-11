// Type-only import -- schedule.ts imports ExerciseRead from this file, so
// this must stay `import type` to avoid a runtime circular import.
import type { TrainingPhase } from './schedule'

export const TARGET_STATS = [
  'strength',
  'agility',
  'intellect',
  'endurance',
  'on_ice_skating',
  'puck_handling',
] as const
export type TargetStat = (typeof TARGET_STATS)[number]

export const TARGET_STAT_LABELS: Record<TargetStat, string> = {
  strength: 'Сила',
  agility: 'Ловкость',
  intellect: 'Интеллект',
  endurance: 'Выносливость',
  // Not "Катание" -- that name is already taken by the "Катание" skill
  // (built partly from this same stat). Same reasoning for puck_handling
  // vs the "Обводка" skill.
  on_ice_skating: 'Скорость на льду',
  puck_handling: 'Владение шайбой',
}

// Shared between ProfilePage's stat detail modal and HomePage's compact one
// -- same copy, kept in one place so the two don't drift.
export const TARGET_STAT_DESCRIPTIONS: Record<TargetStat, string> = {
  strength:
    'Базовая мышечная мощность корпуса и ног. Даёт основу для взрывных движений — старт, бросок — и устойчивость в силовых единоборствах.',
  agility:
    'Скорость реакции, координация и контроль тела в движении. Определяет качество катания, смены направления и работы с шайбой.',
  intellect:
    'Понимание игры: чтение ситуаций, принятие решений, позиционирование. Растёт медленнее физических характеристик и во многом опирается на игровой опыт.',
  endurance:
    'Способность поддерживать интенсивность на протяжении всей игры без потери скорости и силы действий.',
  on_ice_skating:
    'Скорость и техника катания по результатам отдельного теста на льду. Растёт только после прохождения этого теста, независимо от общей физической подготовки.',
  puck_handling:
    'Контроль шайбы клюшкой на скорости по результатам отдельного теста на льду. Растёт только после прохождения этого теста, независимо от общей физической подготовки.',
}

export const EXERCISE_CATEGORIES = ['on_ice', 'off_ice'] as const
export type ExerciseCategory = (typeof EXERCISE_CATEGORIES)[number]

// Same wording as DAY_SESSION_TYPE_LABELS (types/schedule.ts) -- different
// entity, same on_ice/off_ice values, kept as its own map here rather than
// reaching into schedule.ts for two strings.
export const EXERCISE_CATEGORY_LABELS: Record<ExerciseCategory, string> = {
  on_ice: 'Лёд',
  off_ice: 'Сухая',
}

export const EQUIPMENT_TYPES = ['gym', 'home', 'bodyweight'] as const
export type EquipmentType = (typeof EQUIPMENT_TYPES)[number]

export const EQUIPMENT_TYPE_LABELS: Record<EquipmentType, string> = {
  gym: 'Зал',
  home: 'Дом',
  bodyweight: 'Только тело',
}

// Anatomical push/pull/legs/core grouping, used only to softly balance
// off_ice main-block picks (see ScheduleService._apply_muscle_balance).
// Meaningless for on_ice drills and for off_ice cardio/mental work -- those
// exercises carry muscle_group=null, not one of these four values.
export const MUSCLE_GROUPS = ['push', 'pull', 'legs', 'core'] as const
export type MuscleGroup = (typeof MUSCLE_GROUPS)[number]

export const MUSCLE_GROUP_LABELS: Record<MuscleGroup, string> = {
  push: 'Толкающие',
  pull: 'Тянущие',
  legs: 'Ноги',
  core: 'Кор',
}

export interface ExerciseRead {
  id: string
  name: string
  description: string | null
  category: ExerciseCategory
  phase: TrainingPhase
  target_stat: TargetStat
  difficulty_level: number
  equipment_type: EquipmentType
  video_source_type: string | null
  video_source_id: string | null
  target_sets: number | null
  target_reps: number | null
  target_duration_seconds: number | null
  tracks_weight: boolean
  bodyweight_ratio: number | null
  suitable_for_game_day: boolean
  muscle_group: MuscleGroup | null
  // Computed server-side from target_reps (see app/core/rest.py) -- not a
  // stored field, and not part of ExerciseWrite below.
  rest_seconds: number | null
}

// Create/update payload (admin CRUD) -- same shape for both; PATCH on the
// backend accepts a subset, but sending the full form state either way
// keeps the admin form's state management a single object.
export interface ExerciseWrite {
  name: string
  description: string | null
  category: ExerciseCategory
  phase: TrainingPhase
  target_stat: TargetStat
  difficulty_level: number
  equipment_type: EquipmentType
  video_source_type: string | null
  video_source_id: string | null
  target_sets: number | null
  target_reps: number | null
  target_duration_seconds: number | null
  tracks_weight: boolean
  bodyweight_ratio: number | null
  suitable_for_game_day: boolean
  muscle_group: MuscleGroup | null
}
