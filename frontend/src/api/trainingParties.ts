import { apiDeleteAuth, apiGet, apiPostAuth } from './client'
import type {
  TrainingPartyCreatePayload,
  TrainingPartyDetailRead,
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
