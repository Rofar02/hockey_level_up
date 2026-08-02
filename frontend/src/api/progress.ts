import { apiGet } from './client'
import type { TrainingStreakRead, UserStatRead } from '../types/progress'

export function getMyStreak(accessToken: string): Promise<TrainingStreakRead> {
  return apiGet<TrainingStreakRead>('/users/me/streak', accessToken)
}

export function getMyStats(accessToken: string): Promise<UserStatRead[]> {
  return apiGet<UserStatRead[]>('/users/me/stats', accessToken)
}
