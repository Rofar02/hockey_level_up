import { apiGet } from './client'
import type { DayReportRead } from '../types/dayReport'

// «Как прошёл день» (2026-10-10).
export function getDayReport(dateIso: string, accessToken: string): Promise<DayReportRead> {
  return apiGet<DayReportRead>(`/users/me/day-report?date=${dateIso}`, accessToken)
}
