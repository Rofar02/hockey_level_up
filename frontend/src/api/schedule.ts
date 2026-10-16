import { apiGet, apiPatchAuth, apiPostAuth } from './client'
import { pendingBlockResolution, whenQueueLoaded } from '../utils/writeQueue'
import type {
  DayPlanRead,
  ScheduleFeaturesRead,
  WeeklyPlanCreate,
  WeeklyPlanPatch,
  WeeklyPlanPatchResult,
  WeeklyPlanRead,
} from '../types/schedule'

// `optional=1` (15.10): "no week yet" is null, not a 404 -- a new player's
// every start used to leave red 404 lines in the console. The same path
// strings everywhere (utils/offlineWarm.ts too), or the GET cache misses.
export const CURRENT_WEEK_PATH = '/schedule/weekly/current?optional=1'

export function weekPath(weekStartDate: string): string {
  return `/schedule/weekly?week_start_date=${weekStartDate}&optional=1`
}

export function dayPlanPath(dateIso: string): string {
  return `/schedule/day-plan?date=${dateIso}&optional=1`
}

export function getCurrentWeeklyPlan(accessToken: string): Promise<WeeklyPlanRead | null> {
  return apiGet<WeeklyPlanRead | null>(CURRENT_WEEK_PATH, accessToken)
}

// weekStartDate is an ISO date (YYYY-MM-DD, e.g. from toIsoDate) -- explicit
// week, not the server's own "current" alias. Used by NewSchedulePage to
// address today's week and next week unambiguously rather than relying on
// server-side date.today() for both tabs.
export function getWeeklyPlan(weekStartDate: string, accessToken: string): Promise<WeeklyPlanRead | null> {
  return apiGet<WeeklyPlanRead | null>(weekPath(weekStartDate), accessToken)
}

// dateIso is an ISO date (YYYY-MM-DD) -- fetches a single day's plan by
// exact date, independent of which week is "current"/"next" right now.
// null for a date with no DayPlan at all -- future date nothing's been
// generated for, or one outside any WeeklyPlan the user ever had.
export function getDayPlan(dateIso: string, accessToken: string): Promise<DayPlanRead | null> {
  return apiGet<DayPlanRead | null>(dayPlanPath(dateIso), accessToken)
}

// A single day by id, from any week -- TrainingSessionPage/TrainingDiaryPage
// open a day by the id in their URL, which can point at any past week (e.g.
// a DiaryPage entry). 404s for an id that isn't one of the user's own days.
export async function getDayPlanById(dayPlanId: string, accessToken: string): Promise<DayPlanRead> {
  const plan = await apiGet<DayPlanRead>(`/schedule/day-plans/${dayPlanId}`, accessToken)
  return withQueuedResolutions(plan)
}

// Б2: exercises marked done/skipped while their write still waits in the
// offline queue show as done -- a workout reopened without signal (from
// saved data) picks up where the player left off.
async function withQueuedResolutions(plan: DayPlanRead): Promise<DayPlanRead> {
  if (plan.training_session == null) {
    return plan
  }
  await whenQueueLoaded()
  let changed = false
  const blocks = plan.training_session.blocks.map((block) => {
    if (block.completed_at !== null || block.skipped_at !== null) {
      return block
    }
    const queued = pendingBlockResolution(block.id)
    if (queued === null) {
      return block
    }
    changed = true
    return { ...block, ...queued }
  })
  return changed ? { ...plan, training_session: { ...plan.training_session, blocks } } : plan
}

export function createWeeklyPlan(
  payload: WeeklyPlanCreate,
  accessToken: string,
): Promise<WeeklyPlanRead> {
  return apiPostAuth<WeeklyPlanRead>('/schedule/weekly', payload, accessToken)
}

export function patchCurrentWeeklyPlan(
  payload: WeeklyPlanPatch,
  accessToken: string,
): Promise<WeeklyPlanPatchResult> {
  return apiPatchAuth<WeeklyPlanPatchResult>('/schedule/weekly/current', payload, accessToken)
}

// weekStartDate is an ISO date -- same explicit-week addressing as
// getWeeklyPlan, for editing a plan that isn't necessarily "current"
// (e.g. next week's).
export function patchWeeklyPlan(
  weekStartDate: string,
  payload: WeeklyPlanPatch,
  accessToken: string,
): Promise<WeeklyPlanPatchResult> {
  return apiPatchAuth<WeeklyPlanPatchResult>(
    `/schedule/weekly?week_start_date=${weekStartDate}`,
    payload,
    accessToken,
  )
}

// Which optional week features are switched on (release plan step 6).
export function getScheduleFeatures(accessToken: string): Promise<ScheduleFeaturesRead> {
  return apiGet<ScheduleFeaturesRead>('/schedule/features', accessToken)
}
