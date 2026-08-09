import type { TargetStat } from './exercise'

export interface SkillOption {
  id: string
  name: string
  required_level: number
}

export interface UserSkillPreference {
  skill_id: string
  name: string
}

export interface NextMilestoneRead {
  title: string
  threshold: number
  points_remaining: number
}

export interface SkillSummaryRead {
  id: string
  name: string
  value: number
  next_milestone: NextMilestoneRead | null
  required_level: number
}

export interface StatContributionRead {
  stat_type: TargetStat
  weight: number
  effective_value: number
  contribution: number
}

export interface SkillMilestoneStatusRead {
  id: string
  threshold: number
  title: string
  description: string
  achieved: boolean
}

export interface SkillDetailRead {
  id: string
  name: string
  value: number
  stat_breakdown: StatContributionRead[]
  milestones: SkillMilestoneStatusRead[]
}

// -- admin CRUD (raw records, no computed value/progress) --

export interface SkillWrite {
  name: string
  required_level: number
}

export interface SkillStatWeightRead {
  id: string
  skill_id: string
  stat_type: TargetStat
  weight: number
}

export interface SkillStatWeightWrite {
  stat_type: TargetStat
  weight: number
}

export interface SkillTagRead {
  id: string
  skill_id: string
  exercise_id: string
  transfer_note: string
}

export interface SkillTagWrite {
  exercise_id: string
  transfer_note: string
}

// Distinct from SkillMilestoneStatusRead above -- that one is the
// user-progress view (with `achieved`), this is the raw admin record.
export interface SkillMilestoneRead {
  id: string
  skill_id: string
  threshold: number
  title: string
  description: string
}

export interface SkillMilestoneWrite {
  threshold: number
  title: string
  description: string
}
