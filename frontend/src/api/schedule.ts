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

export function getCurrentWeeklyPlan(accessToken: string): Promise<WeeklyPlanRead> {
  return apiGet<WeeklyPlanRead>('/schedule/weekly/current', accessToken)
}

// weekStartDate is an ISO date (YYYY-MM-DD, e.g. from toIsoDate) -- explicit
// week, not the server's own "current" alias. Used by NewSchedulePage to
// address today's week and next week unambiguously rather than relying on
// server-side date.today() for both tabs.
export function getWeeklyPlan(weekStartDate: string, accessToken: string): Promise<WeeklyPlanRead> {
  return apiGet<WeeklyPlanRead>(`/schedule/weekly?week_start_date=${weekStartDate}`, accessToken)
}

// dateIso is an ISO date (YYYY-MM-DD) -- fetches a single day's plan by
// exact date, independent of which week is "current"/"next" right now.
// 404s (via loadOptional at the call site) for a date with no DayPlan at
// all -- future date nothing's been generated for, or one outside any
// WeeklyPlan the user ever had.
export function getDayPlan(dateIso: string, accessToken: string): Promise<DayPlanRead> {
  return apiGet<DayPlanRead>(`/schedule/day-plan?date=${dateIso}`, accessToken)
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
