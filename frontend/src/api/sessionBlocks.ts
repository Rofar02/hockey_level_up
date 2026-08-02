import { apiPostAuth } from './client'
import type { SessionBlockRead } from '../types/schedule'

export function completeSessionBlock(
  blockId: string,
  accessToken: string,
): Promise<SessionBlockRead> {
  return apiPostAuth<SessionBlockRead>(`/session-blocks/${blockId}/complete`, undefined, accessToken)
}
