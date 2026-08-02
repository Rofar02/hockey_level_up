import { apiGet, apiPostAuth } from './client'
import type { AssessmentResult, AssessmentStatus, AssessmentTestPayload } from '../types/assessment'

export function getStatus(accessToken: string): Promise<AssessmentStatus> {
  return apiGet<AssessmentStatus>('/assessment/status', accessToken)
}

export function startFromScratch(accessToken: string): Promise<AssessmentResult> {
  return apiPostAuth<AssessmentResult>('/assessment/start-from-scratch', undefined, accessToken)
}

export function submitTest(
  payload: AssessmentTestPayload,
  accessToken: string,
): Promise<AssessmentResult> {
  return apiPostAuth<AssessmentResult>('/assessment/test', payload, accessToken)
}

export function dismissReassessmentSuggestion(accessToken: string): Promise<void> {
  return apiPostAuth<void>('/assessment/dismiss-reassessment-suggestion', undefined, accessToken)
}
