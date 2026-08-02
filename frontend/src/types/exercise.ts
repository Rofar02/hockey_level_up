export const TARGET_STATS = ['strength', 'agility', 'intellect', 'endurance'] as const
export type TargetStat = (typeof TARGET_STATS)[number]

export const TARGET_STAT_LABELS: Record<TargetStat, string> = {
  strength: 'Сила',
  agility: 'Ловкость',
  intellect: 'Интеллект',
  endurance: 'Выносливость',
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
}
