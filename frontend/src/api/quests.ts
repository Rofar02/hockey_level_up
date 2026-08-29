import { apiGet, apiPostAuth } from './client'
import type { QuestStatusRead } from '../types/quest'

export function getQuestStatus(accessToken: string): Promise<QuestStatusRead[]> {
  return apiGet<QuestStatusRead[]>('/quests/status', accessToken)
}

// Fire-and-forget signal for reference_first_visit -- see
// app/routers/quests.py's own comment. Idempotent, safe to call on every
// ReferencePage load.
export function markReferenceVisited(accessToken: string): Promise<void> {
  return apiPostAuth<void>('/quests/reference-visited', {}, accessToken)
}
