import type { TargetStat } from './exercise'

export interface SkillOption {
  id: string
  name: string
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
