import { apiGet } from './client'
import type { TargetStat } from '../types/exercise'
import type {
  ActivityCalendarDayRead,
  MuscleLoadRead,
  RestDonePhraseRead,
  StatHistoryPointRead,
  TrainingStreakRead,
  UserStatRead,
} from '../types/progress'

export function getMyStreak(accessToken: string): Promise<TrainingStreakRead> {
  return apiGet<TrainingStreakRead>('/users/me/streak', accessToken)
}

export function getRestDonePhrase(accessToken: string): Promise<RestDonePhraseRead> {
  return apiGet<RestDonePhraseRead>('/users/me/rest-done-phrase', accessToken)
}

export function getMyMuscleLoads(accessToken: string): Promise<MuscleLoadRead[]> {
  return apiGet<MuscleLoadRead[]>('/users/me/muscle-loads', accessToken)
}

// `month` is any date within the target month (e.g. the first of the
// month) -- the backend resolves the actual [from, to] range itself.
export function getMyActivityCalendar(
  month: string,
  accessToken: string,
): Promise<ActivityCalendarDayRead[]> {
  return apiGet<ActivityCalendarDayRead[]>(
    `/users/me/activity-calendar?month=${month}`,
    accessToken,
  )
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
