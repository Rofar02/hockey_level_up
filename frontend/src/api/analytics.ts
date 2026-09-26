import { apiGet } from './client'
import type { AnalyticsOverviewRead } from '../types/analytics'

export function getAnalyticsOverview(days: number, accessToken: string): Promise<AnalyticsOverviewRead> {
  return apiGet<AnalyticsOverviewRead>(`/users/me/analytics/overview?days=${days}`, accessToken)
}
