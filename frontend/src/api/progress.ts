import { apiGet } from './client'
import type { TargetStat } from '../types/exercise'
import type { StatHistoryPointRead, TrainingStreakRead, UserStatRead } from '../types/progress'

export function getMyStreak(accessToken: string): Promise<TrainingStreakRead> {
  return apiGet<TrainingStreakRead>('/users/me/streak', accessToken)
}

export function getMyStats(accessToken: string): Promise<UserStatRead[]> {
  return apiGet<UserStatRead[]>('/users/me/stats', accessToken)
}

// Always passes stat_type -- the backend also supports omitting it (every
// stat grouped by type in one response), but the analytics page only ever
// plots one series at a time, so this stays a flat array rather than
// exposing the grouped shape to callers that don't need it.
export function getStatsHistory(
  statType: TargetStat,
  days: number,
  accessToken: string,
): Promise<StatHistoryPointRead[]> {
  return apiGet<StatHistoryPointRead[]>(
    `/users/me/analytics/stats-history?stat_type=${statType}&days=${days}`,
    accessToken,
  )
}
