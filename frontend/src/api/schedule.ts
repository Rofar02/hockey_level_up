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
