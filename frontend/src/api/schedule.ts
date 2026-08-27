import { apiGet, apiPatchAuth, apiPostAuth } from './client'
import type {
  DayPlanRead,
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
