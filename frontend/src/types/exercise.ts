export const TARGET_STATS = ['strength', 'agility', 'intellect', 'endurance'] as const
export type TargetStat = (typeof TARGET_STATS)[number]

export const TARGET_STAT_LABELS: Record<TargetStat, string> = {
  strength: 'Сила',
  agility: 'Ловкость',
  intellect: 'Интеллект',
  endurance: 'Выносливость',
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
}

export const EXERCISE_CATEGORIES = ['on_ice', 'off_ice'] as const
export type ExerciseCategory = (typeof EXERCISE_CATEGORIES)[number]

export const EQUIPMENT_TYPES = ['gym', 'home', 'bodyweight'] as const
export type EquipmentType = (typeof EQUIPMENT_TYPES)[number]

export interface ExerciseRead {
  id: string
  name: string
  description: string | null
  category: ExerciseCategory
  phase: string
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
}
