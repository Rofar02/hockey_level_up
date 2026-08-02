export interface AssessmentStatus {
  has_assessment: boolean
  suggested_reassessment: boolean
}

export interface AssessmentResult {
  agility: number
  strength: number
  endurance: number
  intellect: number
  fitness_tier: string
}

export interface AssessmentTestPayload {
  long_jump_cm: number
  pushups_reps: number
  squats_reps: number
  plank_seconds: number
  run_1km_seconds: number
}
