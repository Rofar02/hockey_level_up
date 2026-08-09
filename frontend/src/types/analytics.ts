// Mirrors app/schemas/analytics.py -- structured data for the summary text,
// not ready-made copy (see utils/analyticsSummary.ts, which assembles the
// actual Russian sentences from this).
import type { TargetStat } from './exercise'

export interface AnalyticsMoverRead {
  // For type: 'stat', this is the raw TargetStat value (e.g. "strength"),
  // not a Russian label -- look it up via TARGET_STAT_LABELS. For 'skill',
  // it's already the skill's real (Russian) name.
  name: string | TargetStat
  type: 'stat' | 'skill'
  delta: number
  current_value: number
}

export interface AnalyticsMilestoneRead {
  skill_name: string
  points_remaining: number
  threshold: number
}

export interface AnalyticsSummaryRead {
  top_gainer: AnalyticsMoverRead
  top_decliner: AnalyticsMoverRead | null
  closest_to_milestone: AnalyticsMilestoneRead | null
  decline_reason: string | null
}
