import type { TargetStat } from './exercise'
import type { DaySessionType } from './schedule'

export interface TrainingDiaryEntryIn {
  note: string | null
}

export interface TrainingDiaryEntryRead {
  id: string
  training_session_id: string
  note: string | null
  created_at: string
  updated_at: string
  // The day's diary reward is credited (once, for a real note on a day
  // that has come).
  rewarded: boolean
  // What this particular save credited -- empty on every other save.
  stat_rewards: Partial<Record<TargetStat, number>>
}

// Mirrors DIARY_REWARD_MIN_CHARS in app/services/training_diary_service.py.
export const DIARY_REWARD_MIN_CHARS = 20

export interface TrainingDiaryEntryListItem {
  id: string
  training_session_id: string
  day_plan_id: string
  date: string
  session_type: DaySessionType
  note: string | null
  created_at: string
  updated_at: string
}
