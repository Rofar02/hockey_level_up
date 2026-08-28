import { apiPostAuth } from './client'
import type { SessionBlockRead } from '../types/schedule'

export function completeSessionBlock(
  blockId: string,
  accessToken: string,
): Promise<SessionBlockRead> {
  return apiPostAuth<SessionBlockRead>(`/session-blocks/${blockId}/complete`, undefined, accessToken)
}

// Warmup/cooldown-only (media-player redesign, 2026-08-28) -- see
// SessionBlockService.skip_block for the server-side phase enforcement.
export function skipSessionBlock(
  blockId: string,
  accessToken: string,
): Promise<SessionBlockRead> {
  return apiPostAuth<SessionBlockRead>(`/session-blocks/${blockId}/skip`, undefined, accessToken)
}

// Stage 1.5 (2026-08-20 planning session, "тренажёр занят"): manual
// single-slot swap, not a session regenerate -- see
// ScheduleService.replace_block_exercise for the substitution rules.
export function replaceSessionBlockExercise(
  blockId: string,
  accessToken: string,
): Promise<SessionBlockRead> {
  return apiPostAuth<SessionBlockRead>(`/session-blocks/${blockId}/replace`, undefined, accessToken)
}
