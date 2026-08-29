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

// Grants a claimable quest's XP -- the player-initiated action behind
// QuestsPage's "Получить" button (XP is never granted automatically just
// because the criteria were met, see app/services/quest_service.py).
export function claimQuest(questId: string, accessToken: string): Promise<QuestStatusRead> {
  return apiPostAuth<QuestStatusRead>(`/quests/${questId}/claim`, {}, accessToken)
}
