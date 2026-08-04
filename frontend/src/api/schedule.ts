import { apiGet, apiPatchAuth, apiPostAuth } from './client'
import type {
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
