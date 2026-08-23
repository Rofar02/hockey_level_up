import { apiGet, apiPutAuth } from './client'
import type {
  TrainingDiaryEntryIn,
  TrainingDiaryEntryListItem,
  TrainingDiaryEntryRead,
} from '../types/trainingDiary'

export function getDiaryEntry(
  trainingSessionId: string,
  accessToken: string,
): Promise<TrainingDiaryEntryRead | null> {
  return apiGet<TrainingDiaryEntryRead | null>(`/training-sessions/${trainingSessionId}/diary`, accessToken)
}

export function saveDiaryEntry(
  trainingSessionId: string,
  body: TrainingDiaryEntryIn,
  accessToken: string,
): Promise<TrainingDiaryEntryRead> {
  return apiPutAuth<TrainingDiaryEntryRead>(
    `/training-sessions/${trainingSessionId}/diary`,
    body,
    accessToken,
  )
}

export function listDiaryEntries(accessToken: string): Promise<TrainingDiaryEntryListItem[]> {
  return apiGet<TrainingDiaryEntryListItem[]>('/users/me/training-diary', accessToken)
}
