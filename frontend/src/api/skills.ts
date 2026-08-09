import { apiDeleteAuth, apiGet, apiPatchAuth, apiPostAuth } from './client'
import type {
  SkillDetailRead,
  SkillMilestoneRead,
  SkillMilestoneWrite,
  SkillOption,
  SkillStatWeightRead,
  SkillStatWeightWrite,
  SkillSummaryRead,
  SkillTagRead,
  SkillTagWrite,
  SkillWrite,
} from '../types/skill'

// Used both by the onboarding skill picker (id/name only) and the profile
// page's skill list (the full summary, incl. progress) -- same endpoint,
// the richer type is a superset so both callers are satisfied.
export function listSkills(accessToken: string): Promise<SkillSummaryRead[]> {
  return apiGet<SkillSummaryRead[]>('/skills', accessToken)
}

export function getSkillDetail(skillId: string, accessToken: string): Promise<SkillDetailRead> {
  return apiGet<SkillDetailRead>(`/skills/${skillId}`, accessToken)
}

// -- admin CRUD: Skill --
//
// Deliberately a distinct GET from listSkills above -- this is the plain
// (id, name) record with no computed value/progress, gated by require_admin
// server-side (see GET /skills/admin).

export function listSkillsAdmin(accessToken: string): Promise<SkillOption[]> {
  return apiGet<SkillOption[]>('/skills/admin', accessToken)
}

export function getSkillAdmin(skillId: string, accessToken: string): Promise<SkillOption> {
  return apiGet<SkillOption>(`/skills/admin/${skillId}`, accessToken)
}

export function createSkill(payload: SkillWrite, accessToken: string): Promise<SkillOption> {
  return apiPostAuth<SkillOption>('/skills', payload, accessToken)
}

export function updateSkill(
  skillId: string,
  payload: SkillWrite,
  accessToken: string,
): Promise<SkillOption> {
  return apiPatchAuth<SkillOption>(`/skills/${skillId}`, payload, accessToken)
}

export function deleteSkill(skillId: string, accessToken: string): Promise<void> {
  return apiDeleteAuth<void>(`/skills/${skillId}`, accessToken)
}

// -- admin CRUD: SkillStatWeight --

export function listStatWeights(
  skillId: string,
  accessToken: string,
): Promise<SkillStatWeightRead[]> {
  return apiGet<SkillStatWeightRead[]>(`/skills/${skillId}/stat-weights`, accessToken)
}

export function createStatWeight(
  skillId: string,
  payload: SkillStatWeightWrite,
  accessToken: string,
): Promise<SkillStatWeightRead> {
  return apiPostAuth<SkillStatWeightRead>(`/skills/${skillId}/stat-weights`, payload, accessToken)
}

export function updateStatWeight(
  skillId: string,
  weightId: string,
  payload: SkillStatWeightWrite,
  accessToken: string,
): Promise<SkillStatWeightRead> {
  return apiPatchAuth<SkillStatWeightRead>(
    `/skills/${skillId}/stat-weights/${weightId}`,
    payload,
    accessToken,
  )
}

export function deleteStatWeight(
  skillId: string,
  weightId: string,
  accessToken: string,
): Promise<void> {
  return apiDeleteAuth<void>(`/skills/${skillId}/stat-weights/${weightId}`, accessToken)
}

// -- admin CRUD: SkillMilestone --

export function listMilestones(skillId: string, accessToken: string): Promise<SkillMilestoneRead[]> {
  return apiGet<SkillMilestoneRead[]>(`/skills/${skillId}/milestones`, accessToken)
}

export function createMilestone(
  skillId: string,
  payload: SkillMilestoneWrite,
  accessToken: string,
): Promise<SkillMilestoneRead> {
  return apiPostAuth<SkillMilestoneRead>(`/skills/${skillId}/milestones`, payload, accessToken)
}

export function updateMilestone(
  skillId: string,
  milestoneId: string,
  payload: SkillMilestoneWrite,
  accessToken: string,
): Promise<SkillMilestoneRead> {
  return apiPatchAuth<SkillMilestoneRead>(
    `/skills/${skillId}/milestones/${milestoneId}`,
    payload,
    accessToken,
  )
}

export function deleteMilestone(
  skillId: string,
  milestoneId: string,
  accessToken: string,
): Promise<void> {
  return apiDeleteAuth<void>(`/skills/${skillId}/milestones/${milestoneId}`, accessToken)
}

// -- admin CRUD: SkillTag --
//
// Only create/delete are exposed here -- the admin UI edits tags from the
// exercise's side (see api/exercises.ts#listExerciseSkillTags), where a tag
// is either added or removed, never edited in place beyond its note (an
// update endpoint exists server-side but the exercise form has no use for
// it yet).

export function createSkillTag(
  skillId: string,
  payload: SkillTagWrite,
  accessToken: string,
): Promise<SkillTagRead> {
  return apiPostAuth<SkillTagRead>(`/skills/${skillId}/tags`, payload, accessToken)
}

export function deleteSkillTag(skillId: string, tagId: string, accessToken: string): Promise<void> {
  return apiDeleteAuth<void>(`/skills/${skillId}/tags/${tagId}`, accessToken)
}
