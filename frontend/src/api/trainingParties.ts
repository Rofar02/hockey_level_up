import { apiDeleteAuth, apiGet, apiPostAuth } from './client'
import type { ExerciseRead } from '../types/exercise'
import type {
  TrainingPartyCreatePayload,
  TrainingPartyDetailRead,
  TrainingPartyExercisesConfirmPayload,
  TrainingPartyInviteRead,
  TrainingPartySummaryRead,
} from '../types/trainingParty'

export function createTrainingParty(
  payload: TrainingPartyCreatePayload,
  accessToken: string,
): Promise<TrainingPartyDetailRead> {
  return apiPostAuth<TrainingPartyDetailRead>('/training-parties', payload, accessToken)
}

export function listMyTrainingParties(accessToken: string): Promise<TrainingPartySummaryRead[]> {
  return apiGet<TrainingPartySummaryRead[]>('/training-parties/me', accessToken)
}

export function listIncomingTrainingPartyInvites(
  accessToken: string,
): Promise<TrainingPartyInviteRead[]> {
  return apiGet<TrainingPartyInviteRead[]>('/training-parties/invites', accessToken)
}

export function getTrainingParty(
  partyId: string,
  accessToken: string,
): Promise<TrainingPartyDetailRead> {
  return apiGet<TrainingPartyDetailRead>(`/training-parties/${partyId}`, accessToken)
}

// Creator-only -- the backend 403s for anyone else.
export function cancelTrainingParty(partyId: string, accessToken: string): Promise<void> {
  return apiDeleteAuth<void>(`/training-parties/${partyId}`, accessToken)
}

export function acceptTrainingPartyInvite(
  partyId: string,
  accessToken: string,
): Promise<TrainingPartyDetailRead> {
  return apiPostAuth<TrainingPartyDetailRead>(`/training-parties/${partyId}/accept`, {}, accessToken)
}

export function declineTrainingPartyInvite(
  partyId: string,
  accessToken: string,
): Promise<TrainingPartyDetailRead> {
  return apiPostAuth<TrainingPartyDetailRead>(`/training-parties/${partyId}/decline`, {}, accessToken)
}

// Creator can't leave -- the backend 409s and points at cancelTrainingParty instead.
export function leaveTrainingParty(partyId: string, accessToken: string): Promise<void> {
  return apiDeleteAuth<void>(`/training-parties/${partyId}/members/me`, accessToken)
}

// Creator-only, never persists anything -- both "Сгенерировать" and the
// recommended-highlighting in "Собрать самому" call this; calling it again
// is "перемешать".
export function suggestTrainingPartyExercises(
  partyId: string,
  accessToken: string,
  count?: number,
): Promise<ExerciseRead[]> {
  const query = count !== undefined ? `?count=${count}` : ''
  return apiPostAuth<ExerciseRead[]>(
    `/training-parties/${partyId}/exercises/suggest${query}`,
    {},
    accessToken,
  )
}

// Creator-only. Materializes payload.exercise_ids as every joined member's
// shared TrainingSession for the party's date.
export function confirmTrainingPartyExercises(
  partyId: string,
  payload: TrainingPartyExercisesConfirmPayload,
  accessToken: string,
): Promise<TrainingPartyDetailRead> {
  return apiPostAuth<TrainingPartyDetailRead>(
    `/training-parties/${partyId}/exercises/confirm`,
    payload,
    accessToken,
  )
}
