import { apiGet } from './client'
import type { AnalyticsSummaryRead } from '../types/analytics'

export function getAnalyticsSummary(
  days: number,
  accessToken: string,
): Promise<AnalyticsSummaryRead> {
  return apiGet<AnalyticsSummaryRead>(`/users/me/analytics/summary?days=${days}`, accessToken)
}
