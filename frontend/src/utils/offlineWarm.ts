// After sign-in, quietly load what a player needs at the rink so it's saved
// for offline use (Б1, 2026-10-13) even if they never opened it online:
// today, this week and next, and today's/tomorrow's workouts in full.
// Failures are ignored. A week that isn't planned yet is null, not a 404
// (`optional=1`, 15.10), and the ice/game report is only asked for on an ice
// or game day -- a gym day's /diary was a 400 on every start.
import { apiGet, warmApiCache } from '../api/client'
import { CURRENT_WEEK_PATH, dayPlanPath, weekPath } from '../api/schedule'
import type { WeeklyPlanRead } from '../types/schedule'
import { addDays, getMondayOfCurrentWeek, parseIsoDate, toIsoDate, todayIsoIn } from './date'

const REPORT_DAY_TYPES = new Set(['on_ice', 'game'])

export async function warmOfflineData(accessToken: string, timeZone: string | null | undefined): Promise<void> {
  const today = todayIsoIn(timeZone)
  const tomorrow = toIsoDate(addDays(parseIsoDate(today), 1))
  const monday = getMondayOfCurrentWeek(parseIsoDate(today))
  warmApiCache(
    [
      dayPlanPath(today),
      weekPath(toIsoDate(monday)),
      weekPath(toIsoDate(addDays(monday, 7))),
      '/users/me/pending-reports',
    ],
    accessToken,
  )
  try {
    const week = await apiGet<WeeklyPlanRead | null>(CURRENT_WEEK_PATH, accessToken)
    if (week === null) {
      return
    }
    const soon = week.day_plans.filter((plan) => plan.date === today || plan.date === tomorrow)
    warmApiCache(
      soon.flatMap((plan) => [
        `/schedule/day-plans/${plan.id}`,
        ...(plan.training_session && REPORT_DAY_TYPES.has(plan.session_type)
          ? [`/training-sessions/${plan.training_session.id}/diary`]
          : []),
      ]),
      accessToken,
    )
  } catch {
    // Offline, or the server is down -- nothing to warm.
  }
}
