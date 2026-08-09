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

export interface OnIceAssessmentStatus {
  has_onice_assessment: boolean
  suggested_onice_reassessment: boolean
}

export interface OnIceAssessmentResult {
  on_ice_skating: number
  puck_handling: number
}

export interface OnIceAssessmentTestPayload {
  on_ice_skating_seconds: number
  puck_handling_seconds: number
}
