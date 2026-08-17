import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import * as assessmentApi from '../api/assessment'
import * as authApi from '../api/auth'
import { ApiError } from '../api/client'
import {
  clearStoredTokens,
  getStoredAccessToken,
  getStoredRefreshToken,
  persistTokens,
  SESSION_EXPIRED_EVENT,
  TOKENS_REFRESHED_EVENT,
} from '../api/tokenStorage'
import type { TokensRefreshedDetail } from '../api/tokenStorage'
import type { UserRead } from '../types/user'
import { AuthContext } from './authContext'
import type { AuthContextValue } from './authContext'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [user, setUser] = useState<UserRead | null>(null)
  const [hasAssessment, setHasAssessment] = useState<boolean | null>(null)
  // Starts true so route guards can hold off redirecting until a reload has
  // had a chance to restore (or fail to restore) a session from
  // localStorage -- otherwise a logged-in user hitting refresh would flash
  // through "logged out" for one render and get bounced to /login before
  // the restore even had a chance to run.
  const [isInitializing, setIsInitializing] = useState(true)

  // Fetches the user + assessment status for a token pair and, only once
  // both succeed, persists the pair and commits it to state -- so a failed
  // restore attempt never leaves half-applied state.
  const applySession = useCallback(async (nextAccessToken: string, nextRefreshToken: string) => {
    const [currentUser, status] = await Promise.all([
      authApi.getCurrentUser(nextAccessToken),
      assessmentApi.getStatus(nextAccessToken),
    ])
    persistTokens(nextAccessToken, nextRefreshToken)
    setAccessToken(nextAccessToken)
    setUser(currentUser)
    setHasAssessment(status.has_assessment)
  }, [])

  useEffect(() => {
    let cancelled = false

    async function restoreSession() {
      const storedAccessToken = getStoredAccessToken()
      const storedRefreshToken = getStoredRefreshToken()
      if (storedAccessToken === null || storedRefreshToken === null) {
        return
      }

      try {
        await applySession(storedAccessToken, storedRefreshToken)
        return
      } catch (err) {
        if (!(err instanceof ApiError) || err.status !== 401) {
          clearStoredTokens()
          return
        }
      }

      // Access token was rejected -- one refresh attempt before giving up.
      try {
        const tokens = await authApi.refresh(storedRefreshToken)
        await applySession(tokens.access_token, tokens.refresh_token)
      } catch {
        clearStoredTokens()
      }
    }

    restoreSession().finally(() => {
      if (!cancelled) {
        setIsInitializing(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [applySession])

  const login = useCallback(
    async (username: string, password: string) => {
      const tokens = await authApi.login(username, password)
      await applySession(tokens.access_token, tokens.refresh_token)
    },
    [applySession],
  )

  const logout = useCallback(() => {
    clearStoredTokens()
    setAccessToken(null)
    setUser(null)
    setHasAssessment(null)
  }, [])

  // client.ts refreshes an expired access token mid-request (see
  // request()'s 401 handling) since it can't reach this context directly.
  // These events keep in-memory state in sync with what it wrote to
  // localStorage, so the next call doesn't pay for its own redundant
  // refresh, and so an unrecoverable expiry (refresh token also rejected)
  // logs the user out and bounces them to /login via ProtectedRoute instead
  // of leaving every request silently 401ing until a hard reload.
  useEffect(() => {
    function handleTokensRefreshed(event: Event) {
      const { accessToken: nextAccessToken } = (event as CustomEvent<TokensRefreshedDetail>).detail
      setAccessToken(nextAccessToken)
    }

    function handleSessionExpired() {
      setAccessToken(null)
      setUser(null)
      setHasAssessment(null)
    }

    window.addEventListener(TOKENS_REFRESHED_EVENT, handleTokensRefreshed)
    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired)
    return () => {
      window.removeEventListener(TOKENS_REFRESHED_EVENT, handleTokensRefreshed)
      window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired)
    }
  }, [])

  const markAssessmentComplete = useCallback(() => {
    setHasAssessment(true)
  }, [])

  const updateUser = useCallback((nextUser: UserRead) => {
    setUser(nextUser)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      accessToken,
      user,
      hasAssessment,
      isAuthenticated: accessToken !== null,
      isInitializing,
      login,
      logout,
      markAssessmentComplete,
      updateUser,
    }),
    [accessToken, user, hasAssessment, isInitializing, login, logout, markAssessmentComplete, updateUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
