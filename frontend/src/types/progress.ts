import type { TargetStat } from './exercise'

export interface TrainingStreakRead {
  current_streak: number
  longest_streak: number
  last_activity_date: string | null
}

export const STAT_TRENDS = ['up', 'down'] as const
export type StatTrend = (typeof STAT_TRENDS)[number]

export interface UserStatRead {
  stat_type: TargetStat
  current_value: number
  effective_value: number
  trend: StatTrend
  idle_days: number
  decay_active: boolean
  last_updated_at: string
}

// Shared shape for both GET /users/me/analytics/stats-history and
// .../skills-history -- {date, value} points over a `days` window.
export interface StatHistoryPointRead {
  date: string
  value: number
}
