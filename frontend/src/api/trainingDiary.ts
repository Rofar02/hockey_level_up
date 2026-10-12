import { apiGet, apiPostAuth, apiPutAuth } from './client'
import type {
  IceFocusRead,
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

// POST, not GET (review 12.10): the focus as shown to the player -- the
// server pins it for the day when it's the ice day itself.
export function getIceFocus(trainingSessionId: string, accessToken: string): Promise<IceFocusRead | null> {
  return apiPostAuth<IceFocusRead | null>(`/training-sessions/${trainingSessionId}/focus`, {}, accessToken)
}
