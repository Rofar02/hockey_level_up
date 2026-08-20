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
    'Скорость и техника катания по льду. Определяет быстроту стартов, поворотов и общую скорость передвижения на площадке.',
  puck_handling:
    'Контроль шайбы клюшкой на высокой скорости. Определяет качество обводки и уверенность в приёме и передаче шайбы.',
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

// Stage 2.2 (2026-08-20 planning session): replaced the old gym/home/
// bodyweight tier. An exercise now requires a *set* of specific items (see
// EquipmentItemsReplace, managed via dedicated
// /exercises/{id}/equipment-items endpoints, not part of ExerciseRead/
// ExerciseWrite -- same two-step pattern as movement_patterns/
// muscle-groups), checked as a subset against a user's own owned items
// (see UserRead.has_gym_access + api/users.ts's equipment-items
// endpoints). No equivalence grouping -- kettlebell/dumbbells/barbell are
// different exercises technique-wise, tagging is always the concrete item.
export const EQUIPMENT_ITEMS = [
  'kettlebell',
  'dumbbells',
  'barbell',
  'resistance_band',
  'pull_up_bar',
  'jump_rope',
  'foam_roller',
  'step_platform',
  'slide_board',
  'medicine_ball',
] as const
export type EquipmentItem = (typeof EQUIPMENT_ITEMS)[number]

export const EQUIPMENT_ITEM_LABELS: Record<EquipmentItem, string> = {
  kettlebell: 'Гиря',
  dumbbells: 'Гантели',
  barbell: 'Штанга',
  resistance_band: 'Резина/эспандер',
  pull_up_bar: 'Турник',
  jump_rope: 'Скакалка',
  foam_roller: 'Мяч для раскатки/МФР-ролик',
  step_platform: 'Степ-платформа',
  slide_board: 'Слайд-борд',
  medicine_ball: 'Медбол',
}

// Detailed anatomical taxonomy (Stage 2.1, 2026-08-20 planning session) --
// replaced the old push/pull/legs/core grouping, which couldn't tell a
// squat from a lunge apart. Multi-value + weighted per exercise (see
// MuscleGroupWeight below), managed via dedicated
// /exercises/{id}/muscle-groups endpoints, not part of
// ExerciseRead/ExerciseWrite -- same two-step pattern as movement_patterns.
export const MUSCLE_GROUPS = [
  'quads',
  'hamstrings',
  'glutes',
  'chest',
  'back',
  'shoulders',
  'core',
  'calves',
] as const
export type MuscleGroup = (typeof MUSCLE_GROUPS)[number]

export const MUSCLE_GROUP_LABELS: Record<MuscleGroup, string> = {
  quads: 'Квадрицепс',
  hamstrings: 'Задняя поверхность бедра',
  glutes: 'Ягодицы',
  chest: 'Грудь',
  back: 'Спина',
  shoulders: 'Плечи',
  core: 'Кор',
  calves: 'Икры',
}

export interface MuscleGroupWeight {
  muscle_group: MuscleGroup
  weight: number
}

// Not yet classified on most exercises -- null is "not yet classified", not
// a default. Feeds a future rest-time formula (not used yet).
export const STIMULUS_TYPES = ['strength', 'power', 'endurance', 'skill', 'mobility'] as const
export type StimulusType = (typeof STIMULUS_TYPES)[number]

export const STIMULUS_TYPE_LABELS: Record<StimulusType, string> = {
  strength: 'Сила',
  power: 'Мощность',
  endurance: 'Выносливость',
  skill: 'Навык',
  mobility: 'Мобильность',
}

// Will eventually replace the implicit target_sets/rep_range_min/
// rep_range_max vs target_duration_seconds discriminator -- not enforced
// yet, most exercises are still unclassified (null).
export const EXERCISE_TYPES = ['sets_reps', 'duration'] as const
export type ExerciseType = (typeof EXERCISE_TYPES)[number]

export const EXERCISE_TYPE_LABELS: Record<ExerciseType, string> = {
  sets_reps: 'Подходы/повторения',
  duration: 'Время',
}

// Multi-value tag (many per exercise), managed via dedicated
// /exercises/{id}/movement-patterns endpoints, not part of
// ExerciseRead/ExerciseWrite -- mirrors how skill tags are handled
// separately from core exercise CRUD.
export const MOVEMENT_PATTERNS = [
  'hip_hinge',
  'squat',
  'push',
  'pull',
  'rotation',
  'ankle_mobility',
  'hip_mobility',
  'shoulder_mobility',
  'wrist_mobility',
  'core',
  'locomotion',
  // 2026-08-19: for exercises that are stick-skill or general coordination/
  // reaction/balance work, not a strength/mobility movement -- see
  // app/models/exercise.py's MovementPattern docstring for why balance
  // folds into coordination here rather than getting its own value.
  'stick_handling',
  'coordination',
] as const
export type MovementPattern = (typeof MOVEMENT_PATTERNS)[number]

export const MOVEMENT_PATTERN_LABELS: Record<MovementPattern, string> = {
  hip_hinge: 'Хип-хиндж',
  squat: 'Присед',
  push: 'Толчок',
  pull: 'Тяга',
  rotation: 'Ротация',
  ankle_mobility: 'Мобильность голеностопа',
  hip_mobility: 'Мобильность таза',
  shoulder_mobility: 'Мобильность плечевого пояса',
  wrist_mobility: 'Мобильность запястья',
  core: 'Кор',
  locomotion: 'Локомоция',
  stick_handling: 'Владение клюшкой',
  coordination: 'Координация и реакция',
}

// The 5 stages of a warmup, in the order ScheduleService._pick_warmup_complex
// walks them (soft tissue prep -> raise pulse/temperature -> joint mobility
// -> muscle activation -> sport-specific dynamic movement) -- meaningless
// outside phase=WARMUP. An exercise with phase=warmup and this left unset
// never gets picked into the assembled warmup complex, no matter how it's
// otherwise tagged -- see the AdminExercisesPage warning copy next to this
// field.
export const WARMUP_STAGES = [
  'soft_tissue',
  'raise',
  'joint_mobility',
  'activation',
  'dynamic',
] as const
export type WarmupStage = (typeof WARMUP_STAGES)[number]

export const WARMUP_STAGE_LABELS: Record<WarmupStage, string> = {
  soft_tissue: 'Миофасциальный релиз',
  raise: 'Подъём пульса',
  joint_mobility: 'Суставная мобильность',
  activation: 'Активация мышц',
  dynamic: 'Динамическая (спортивная)',
}

export interface ExerciseRead {
  id: string
  name: string
  description: string | null
  category: ExerciseCategory
  phase: TrainingPhase
  // Not a raw model passthrough on the backend -- assembled server-side
  // from ExerciseTargetStat rows, ordered; index 0 is the "primary" stat
  // ScheduleService buckets on for diversity. Not part of ExerciseWrite --
  // set via PUT /exercises/{id}/target-stats (see api/exercises.ts), same
  // two-step create-then-tag flow as movement_patterns/skill-tags.
  target_stats: TargetStat[]
  difficulty_level: number
  video_source_type: string | null
  video_source_id: string | null
  target_sets: number | null
  rep_range_min: number | null
  rep_range_max: number | null
  target_duration_seconds: number | null
  tracks_weight: boolean
  bodyweight_ratio: number | null
  suitable_for_game_day: boolean
  // Stage 2.4: bilateral vs unilateral load, meaningful only for squat/
  // hip_hinge exercises -- null means not yet classified.
  is_unilateral: boolean | null
  stimulus_type: StimulusType | null
  exercise_type: ExerciseType | null
  warmup_stage: WarmupStage | null
  // Computed server-side from stimulus_type/difficulty_level (see
  // app/core/rest.py) -- not a stored field, and not part of ExerciseWrite
  // below.
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
  difficulty_level: number
  video_source_type: string | null
  video_source_id: string | null
  target_sets: number | null
  rep_range_min: number | null
  rep_range_max: number | null
  target_duration_seconds: number | null
  tracks_weight: boolean
  bodyweight_ratio: number | null
  suitable_for_game_day: boolean
  is_unilateral: boolean | null
  stimulus_type: StimulusType | null
  exercise_type: ExerciseType | null
  warmup_stage: WarmupStage | null
}
