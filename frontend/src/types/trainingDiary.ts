import type { TargetStat } from './exercise'
import type { DaySessionType } from './schedule'

export type IceEffort = 'easy' | 'normal' | 'hard'
export type IceHighlight = 'skating' | 'passing' | 'shooting' | 'game_reading'
export type GameResult = 'win' | 'draw' | 'loss'
export type GameWorkOn = 'skating' | 'defense' | 'shooting' | 'positioning'

export const ICE_DURATIONS = [45, 60, 75, 90] as const

export const ICE_EFFORT_LABELS: Record<IceEffort, string> = {
  easy: 'Легко',
  normal: 'Нормально',
  hard: 'На пределе',
}

export const ICE_HIGHLIGHT_LABELS: Record<IceHighlight, string> = {
  skating: 'Катание',
  passing: 'Передачи',
  shooting: 'Броски',
  game_reading: 'Чтение игры',
}

export const GAME_RESULT_LABELS: Record<GameResult, string> = {
  win: 'Победа',
  draw: 'Ничья',
  loss: 'Поражение',
}

export const GAME_WORK_ON_LABELS: Record<GameWorkOn, string> = {
  skating: 'Катание',
  defense: 'Игра в защите',
  shooting: 'Броски',
  positioning: 'Выбор позиции',
}

// The report after an ice day or a game (2026-10-08) -- mirrors
// DiaryReportIn in app/schemas/training_diary.py.
export interface DiaryReportIn {
  skipped: boolean
  duration_minutes?: number | null
  effort?: IceEffort | null
  highlights?: IceHighlight[]
  game_result?: GameResult | null
  // Left out for a goalie.
  goals?: number | null
  assists?: number | null
  shots?: number | null
  self_rating?: number | null
  work_on?: GameWorkOn[]
  share_rating_with_coach?: boolean
}

export interface TrainingDiaryEntryIn {
  note: string | null
  // Omitted on a note-only save: the earlier report stays as it is.
  report?: DiaryReportIn
}

export interface TrainingDiaryEntryRead {
  id: string
  training_session_id: string
  note: string | null
  created_at: string
  updated_at: string
  reported_at: string | null
  skipped: boolean
  duration_minutes: number | null
  effort: IceEffort | null
  highlights: IceHighlight[] | null
  game_result: GameResult | null
  goals: number | null
  assists: number | null
  shots: number | null
  self_rating: number | null
  work_on: GameWorkOn[] | null
  share_rating_with_coach: boolean
  // The day's reward is credited (once, for a submitted report on a day
  // that has come, within REPORT_REWARD_WINDOW_DAYS).
  rewarded: boolean
  // What this particular save credited -- empty/0 on every other save.
  stat_rewards: Partial<Record<TargetStat, number>>
  xp_reward: number
}

// Mirrors REPORT_REWARD_WINDOW_DAYS in app/services/training_diary_service.py.
export const REPORT_REWARD_WINDOW_DAYS = 3

export interface TrainingDiaryEntryListItem {
  id: string
  training_session_id: string
  day_plan_id: string
  date: string
  session_type: DaySessionType
  note: string | null
  created_at: string
  updated_at: string
  reported_at: string | null
  skipped: boolean
  duration_minutes: number | null
  effort: IceEffort | null
  game_result: GameResult | null
  goals: number | null
  assists: number | null
  shots: number | null
  highlights: IceHighlight[] | null
  self_rating: number | null
  work_on: GameWorkOn[] | null
}
