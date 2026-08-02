import { apiGet } from './client'
import type { SkillDetailRead, SkillSummaryRead } from '../types/skill'

// Used both by the onboarding skill picker (id/name only) and the profile
// page's skill list (the full summary, incl. progress) -- same endpoint,
// the richer type is a superset so both callers are satisfied.
export function listSkills(accessToken: string): Promise<SkillSummaryRead[]> {
  return apiGet<SkillSummaryRead[]>('/skills', accessToken)
}

export function getSkillDetail(skillId: string, accessToken: string): Promise<SkillDetailRead> {
  return apiGet<SkillDetailRead>(`/skills/${skillId}`, accessToken)
}
