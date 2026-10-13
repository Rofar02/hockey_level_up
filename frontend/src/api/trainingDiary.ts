import { apiGet, apiPostAuth, apiPutAuth, readWithOfflineCopy } from './client'
import { enqueueWrite, isQueueEnabled } from '../utils/writeQueue'
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
  if (isQueueEnabled()) {
    // Б2: the ice/game report (or "не был на льду") written in the locker
    // room with no signal still counts -- it waits in the queue.
    return enqueueWrite({
      method: 'PUT',
      path: `/training-sessions/${trainingSessionId}/diary`,
      body: { ...body },
      label: body.report ? 'Отчёт о льде' : 'Заметка',
      optimistic: (performedAt) => ({
        ...emptyEntry(trainingSessionId, performedAt),
        note: body.note ?? null,
        queued: true,
      }),
    })
  }
  return apiPutAuth<TrainingDiaryEntryRead>(
    `/training-sessions/${trainingSessionId}/diary`,
    body,
    accessToken,
  )
}

function emptyEntry(trainingSessionId: string, at: string): TrainingDiaryEntryRead {
  return {
    id: `pending-${trainingSessionId}`,
    training_session_id: trainingSessionId,
    note: null,
    created_at: at,
    updated_at: at,
    reported_at: at,
    skipped: false,
    duration_minutes: null,
    effort: null,
    highlights: null,
    focus_id: null,
    focus_result: null,
    game_result: null,
    goals: null,
    assists: null,
    shots: null,
    self_rating: null,
    work_on: null,
    share_rating_with_coach: false,
    rewarded: false,
    stat_rewards: {},
    xp_reward: 0,
  }
}

export function listDiaryEntries(accessToken: string): Promise<TrainingDiaryEntryListItem[]> {
  return apiGet<TrainingDiaryEntryListItem[]>('/users/me/training-diary', accessToken)
}

// POST, not GET (review 12.10): the focus as shown to the player -- the
// server pins it for the day when it's the ice day itself.
// Kept for offline use like the GETs (Б1): ice prep is read at the rink.
export function getIceFocus(trainingSessionId: string, accessToken: string): Promise<IceFocusRead | null> {
  return readWithOfflineCopy(`focus:${trainingSessionId}`, () =>
    apiPostAuth<IceFocusRead | null>(`/training-sessions/${trainingSessionId}/focus`, {}, accessToken),
  )
}
