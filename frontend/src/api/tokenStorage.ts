// Shared by AuthContext (which owns the in-memory accessToken/user state)
// and client.ts (which needs raw localStorage access to silently refresh an
// expired access token mid-request, without a React context on hand).

import type { UserRead } from '../types/user'

const ACCESS_TOKEN_KEY = 'hlu_access_token'
const REFRESH_TOKEN_KEY = 'hlu_refresh_token'
// The last /auth/me answer (+ assessment status) that came back fine -- what
// the app shows when it starts without a connection (А1, 2026-10-13), so no
// signal at the rink never looks like being logged out.
const SESSION_SNAPSHOT_KEY = 'hlu_session_snapshot'

export interface SessionSnapshot {
  user: UserRead
  hasAssessment: boolean
}

export function getStoredAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function persistTokens(accessToken: string, refreshToken: string) {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
}

export function clearStoredTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(SESSION_SNAPSHOT_KEY)
}

export function getSessionSnapshot(): SessionSnapshot | null {
  try {
    const raw = localStorage.getItem(SESSION_SNAPSHOT_KEY)
    if (raw === null) {
      return null
    }
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed === 'object' && parsed !== null && 'user' in parsed && 'hasAssessment' in parsed) {
      return parsed as SessionSnapshot
    }
  } catch {
    // Corrupt or unavailable storage -- behave as if there were none.
  }
  return null
}

export function persistSessionSnapshot(snapshot: SessionSnapshot) {
  try {
    localStorage.setItem(SESSION_SNAPSHOT_KEY, JSON.stringify(snapshot))
  } catch {
    // Storage full or blocked: only the offline start loses out.
  }
}

// The server itself said no (401/403) -- the only case a session is really
// over. A network error, a 5xx or a 429 is "try again later", never a logout.
export function isAuthRejection(err: unknown): boolean {
  return (
    typeof err === 'object' &&
    err !== null &&
    'status' in err &&
    ((err as { status: unknown }).status === 401 || (err as { status: unknown }).status === 403)
  )
}

// client.ts dispatches these on `window` after a silent mid-request refresh
// so AuthContext can keep its in-memory accessToken in sync -- otherwise
// every request after the first expiry would pay for its own refresh
// round-trip until the next hard reload.
export const TOKENS_REFRESHED_EVENT = 'hlu:tokens-refreshed'
export const SESSION_EXPIRED_EVENT = 'hlu:session-expired'

export interface TokensRefreshedDetail {
  accessToken: string
  refreshToken: string
}
