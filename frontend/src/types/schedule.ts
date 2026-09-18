import type { ExerciseRead } from './exercise'

export const DAY_SESSION_TYPES = ['on_ice', 'off_ice', 'rest', 'game'] as const
export type DaySessionType = (typeof DAY_SESSION_TYPES)[number]

export const DAY_SESSION_TYPE_LABELS: Record<DaySessionType, string> = {
  on_ice: 'Лёд',
  off_ice: 'Сухая',
  rest: 'Отдых',
  game: 'Игра',
}

// Shared icon/color language for session types, used anywhere a day/session
// needs to be told apart at a glance (Неделя, главный экран TodayCard).
// Colors reuse the app's only two accents rather than inventing new ones:
// accent-ice for on_ice (literal match), accent-persimmon for game (same
// "this one's a big deal" role it already plays for streak/CTAs). off_ice
// gets plain bright text (still distinct from rest's muted gray) and rest
// stays muted -- there's nothing to plan for it.
export const SESSION_TYPE_ICONS: Record<DaySessionType, string> = {
  on_ice: 'ti-ice-skating',
  off_ice: 'ti-barbell',
  rest: 'ti-moon',
  game: 'ti-shirt-sport',
}

export const SESSION_TYPE_COLORS: Record<DaySessionType, string> = {
  on_ice: 'text-accent-ice',
  off_ice: 'text-[#F5F7FA]',
  rest: 'text-[#8A94A6]',
  game: 'text-accent-persimmon',
}

// 'puck' (P3 item #8): the puck-ownership module's own phase, appended
// last as an optional tail-on to a normal OFF_ICE session -- see
// ScheduleService._pick_puck_module_exercises.
export const TRAINING_PHASES = ['warmup', 'main', 'cooldown', 'puck'] as const
export type TrainingPhase = (typeof TRAINING_PHASES)[number]

export interface DayPlanIn {
  date: string
  session_type: DaySessionType
}

export interface WeeklyPlanCreate {
  days: DayPlanIn[]
}

// Populated only by SessionBlockService.complete_block, only when
// completing that block triggered a bodyweight-escalation swap -- names
// only, display data for SessionCompleteModal's card, not IDs to reload
// anything by.
export interface CeilingEscalationRead {
  old_exercise_name: string
  new_exercise_name: string
}

export interface SessionBlockRead {
  id: string
  phase: TrainingPhase
  order: number
  completed_at: string | null
  skipped_at: string | null
  exercise: ExerciseRead
  ceiling_escalations: CeilingEscalationRead[]
}

export interface TrainingSessionRead {
  id: string
  phase_split: Partial<Record<TrainingPhase, number>>
  duration_seconds: number
  blocks: SessionBlockRead[]
  // null for off_ice/rest (the diary step doesn't apply there at all);
  // for on_ice/game, true as soon as any TrainingDiaryEntry row exists
  // for this session, including a quietly-skipped one with no note.
  has_diary_entry: boolean | null
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
