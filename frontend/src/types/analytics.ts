// Mirrors app/schemas/analytics.py's overview response.
import type { TargetStat } from './exercise'

// -- GET /users/me/analytics/overview: the whole Analytics screen --

export interface AnalyticsInsightRead {
  kind: 'decline' | 'records' | 'milestone' | 'regularity'
  tone: 'good' | 'warning' | 'neutral'
  title: string
  detail: string
  action: 'ask_coach' | 'records' | null
  // The ready question "Спросить тренера" opens the chat with.
  coach_prompt: string | null
}

export interface AnalyticsStatRead {
  stat: TargetStat
  current_value: number
  delta: number
  skipped_dates: string[]
  planned_blocks: number
}

export interface AnalyticsRecordRead {
  exercise_name: string
  unit: 'kg' | 'reps' | 'seconds'
  before: number
  after: number
  achieved_on: string
}

export type AnalyticsDayStatus = 'done' | 'team' | 'skipped' | 'rest' | 'future' | 'none'

export interface AnalyticsRegularityRead {
  planned_sessions: number
  completed_sessions: number
  streak_days: number
  team_going: number | null
  team_total: number | null
  // Four Monday-started weeks ending with the current one.
  calendar: { date: string; status: AnalyticsDayStatus }[]
  most_skipped: { exercise_name: string; count: number }[]
}

export interface AnalyticsLoadWeekRead {
  week_start: string
  tonnage_kg: number
  sets: number
  hard_share: number | null
}

export type AnalyticsMuscleGroup = 'legs' | 'core' | 'back' | 'chest_shoulders' | 'arms'

export interface AnalyticsOverviewRead {
  days: number
  insights: AnalyticsInsightRead[]
  stats: AnalyticsStatRead[]
  records: AnalyticsRecordRead[]
  regularity: AnalyticsRegularityRead
  load: { weeks: AnalyticsLoadWeekRead[]; warning: string | null }
  balance: {
    groups: { group: AnalyticsMuscleGroup; share: number }[]
    pull_blocks: number
    push_blocks: number
    note: string | null
  }
}
