// After sign-in, quietly load what a player needs at the rink so it's saved
// for offline use (Б1, 2026-10-13) even if they never opened it online:
// today, this week and next, and today's/tomorrow's workouts in full.
// Failures are ignored (a week that isn't planned yet just 404s).
import { apiGet, warmApiCache } from '../api/client'
import type { WeeklyPlanRead } from '../types/schedule'
import { addDays, getMondayOfCurrentWeek, parseIsoDate, toIsoDate, todayIsoIn } from './date'

export async function warmOfflineData(accessToken: string, timeZone: string | null | undefined): Promise<void> {
  const today = todayIsoIn(timeZone)
  const tomorrow = toIsoDate(addDays(parseIsoDate(today), 1))
  const monday = getMondayOfCurrentWeek(parseIsoDate(today))
  warmApiCache(
    [
      `/schedule/day-plan?date=${today}`,
      `/schedule/weekly?week_start_date=${toIsoDate(monday)}`,
      `/schedule/weekly?week_start_date=${toIsoDate(addDays(monday, 7))}`,
      '/users/me/pending-reports',
    ],
    accessToken,
  )
  try {
    const week = await apiGet<WeeklyPlanRead>('/schedule/weekly/current', accessToken)
    const soon = week.day_plans.filter((plan) => plan.date === today || plan.date === tomorrow)
    warmApiCache(
      soon.flatMap((plan) => [
        `/schedule/day-plans/${plan.id}`,
        ...(plan.training_session ? [`/training-sessions/${plan.training_session.id}/diary`] : []),
      ]),
      accessToken,
    )
  } catch {
    // No plan yet, or offline -- nothing to warm.
  }
}
