import { apiGet } from './client'
import type { DaySessionType } from '../types/schedule'

// Ice and game days over without a report (2026-10-10): the ice reaches the
// muscle map only through its report.
export interface PendingReportRead {
  day_plan_id: string
  date: string
  session_type: DaySessionType
  team_event_id: string | null
}

export function getPendingReports(accessToken: string): Promise<PendingReportRead[]> {
  return apiGet<PendingReportRead[]>('/users/me/pending-reports', accessToken)
}

export function pendingReportLabel(report: PendingReportRead, todayIso: string): string {
  const isGame = report.session_type === 'game'
  const yesterday = new Date()
  yesterday.setDate(yesterday.getDate() - 1)
  const pad = (n: number) => String(n).padStart(2, '0')
  const yesterdayIso = `${yesterday.getFullYear()}-${pad(yesterday.getMonth() + 1)}-${pad(yesterday.getDate())}`
  if (report.date === todayIso) return isGame ? 'Отметьте сегодняшнюю игру' : 'Отметьте сегодняшний лёд'
  if (report.date === yesterdayIso) return isGame ? 'Отметьте вчерашнюю игру' : 'Отметьте вчерашний лёд'
  const [, month, day] = report.date.split('-')
  return `Отметьте ${isGame ? 'игру' : 'лёд'} ${day}.${month}`
}
