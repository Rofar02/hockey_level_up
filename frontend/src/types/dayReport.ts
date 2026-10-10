import type { TrainingPhase, DaySessionType } from './schedule'

// «Как прошёл день» -- GET /users/me/day-report (2026-10-10).
export interface DayReportSetRead {
  weight_kg: number | null
  reps: number | null
  seconds: number | null
}

export interface DayReportExerciseRead {
  name: string
  phase: TrainingPhase
  done: boolean
  skipped: boolean
  sets: DayReportSetRead[]
  feedback: string | null
}

export interface DayReportIceRead {
  skipped: boolean
  duration_minutes: number | null
  effort: 'easy' | 'normal' | 'hard' | null
  focus_title: string | null
  focus_result: 'done' | 'partial' | 'missed' | null
  game_result: 'win' | 'draw' | 'loss' | null
  goals: number | null
  assists: number | null
  note: string | null
}

export interface DayReportTrainingRead {
  day_plan_id: string
  session_type: DaySessionType
  time_of_day: 'morning' | 'evening' | null
  team_event_id: string | null
  exercises_done: number
  exercises_total: number
  sets_total: number
  tonnage_kg: number
  minutes: number | null
  exercises: DayReportExerciseRead[]
  ice: DayReportIceRead | null
}

export interface DayReportRead {
  date: string
  trainings: DayReportTrainingRead[]
  muscles: { muscle_group: string; intensity: number }[]
  stats: { stat: string; before: number; after: number }[]
  sets_total: number
  tonnage_kg: number
  exercises_done: number
}
