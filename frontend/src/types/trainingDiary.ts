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
}

export interface TrainingDiaryEntryListItem {
  id: string
  training_session_id: string
  date: string
  session_type: DaySessionType
  note: string | null
  created_at: string
  updated_at: string
}
