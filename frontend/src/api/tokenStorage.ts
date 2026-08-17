// Shared by AuthContext (which owns the in-memory accessToken/user state)
// and client.ts (which needs raw localStorage access to silently refresh an
// expired access token mid-request, without a React context on hand).

const ACCESS_TOKEN_KEY = 'hlu_access_token'
const REFRESH_TOKEN_KEY = 'hlu_refresh_token'

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
