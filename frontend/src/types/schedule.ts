import type { ExerciseRead } from './exercise'

export const DAY_SESSION_TYPES = ['on_ice', 'off_ice', 'rest', 'game'] as const
export type DaySessionType = (typeof DAY_SESSION_TYPES)[number]

export const DAY_SESSION_TYPE_LABELS: Record<DaySessionType, string> = {
  on_ice: 'Лёд',
  off_ice: 'Сухая',
  rest: 'Отдых',
  game: 'Игра',
}

export const TRAINING_PHASES = ['warmup', 'main', 'cooldown'] as const
export type TrainingPhase = (typeof TRAINING_PHASES)[number]

export interface DayPlanIn {
  date: string
  session_type: DaySessionType
}

export interface WeeklyPlanCreate {
  days: DayPlanIn[]
}

export interface SessionBlockRead {
  id: string
  phase: TrainingPhase
  order: number
  completed_at: string | null
  exercise: ExerciseRead
}

export interface TrainingSessionRead {
  id: string
  phase_split: Partial<Record<TrainingPhase, number>>
  blocks: SessionBlockRead[]
}

export interface DayPlanRead {
  id: string
  date: string
  session_type: DaySessionType
  training_session: TrainingSessionRead | null
}

export interface WeeklyPlanRead {
  id: string
  week_start_date: string
  day_plans: DayPlanRead[]
}

export interface WeeklyPlanPatch {
  days: DayPlanIn[]
}

export interface ScheduleConflictRead {
  date: string
  detail: string
}

export interface WeeklyPlanPatchResult {
  weekly_plan: WeeklyPlanRead
  conflicts: ScheduleConflictRead[]
}
