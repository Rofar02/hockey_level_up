import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import * as assessmentApi from '../api/assessment'
import * as authApi from '../api/auth'
import { clearApiCache } from '../api/client'
import {
  clearStoredTokens,
  getStoredAccessToken,
  getStoredRefreshToken,
  getSessionSnapshot,
  isAuthRejection,
  persistSessionSnapshot,
  persistTokens,
  SESSION_EXPIRED_EVENT,
  TOKENS_REFRESHED_EVENT,
} from '../api/tokenStorage'
import type { TokensRefreshedDetail } from '../api/tokenStorage'
import type { UserRead } from '../types/user'
import { dropLocalPushSubscription, resyncPushSubscription } from '../push'
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

  // True while the app runs on the saved snapshot because the server could
  // not be reached at start -- the next "online" / return to the app checks
  // the session for real.
  const needsRevalidation = useRef(false)

  // Fetches the user + assessment status for a token pair and, only once
  // both succeed, commits it to state. The pair is stored first: if a 401
  // inside makes client.ts refresh it, the rotated pair it writes is the one
  // kept -- never overwritten with the already-spent one passed in here.
  const applySession = useCallback(async (nextAccessToken: string, nextRefreshToken: string) => {
    // Another account's cached answers must never show for this one.
    clearApiCache()
    persistTokens(nextAccessToken, nextRefreshToken)
    const [currentUser, status] = await Promise.all([
      authApi.getCurrentUser(nextAccessToken),
      assessmentApi.getStatus(nextAccessToken),
    ])
    const storedAccessToken = getStoredAccessToken() ?? nextAccessToken
    persistTokens(storedAccessToken, getStoredRefreshToken() ?? nextRefreshToken)
    persistSessionSnapshot({ user: currentUser, hasAssessment: status.has_assessment })
    needsRevalidation.current = false
    setAccessToken(storedAccessToken)
    setUser(currentUser)
    setHasAssessment(status.has_assessment)
  }, [])

  // Re-checks the stored session. Tokens go only when the server itself
  // rejects them (401/403 after client.ts's own refresh attempt); no signal,
  // a 5xx or a 429 keep the player in, on the last snapshot (А1, 2026-10-13).
  const revalidateSession = useCallback(async () => {
    const storedAccessToken = getStoredAccessToken()
    const storedRefreshToken = getStoredRefreshToken()
    if (storedAccessToken === null || storedRefreshToken === null) {
      return
    }
    try {
      await applySession(storedAccessToken, storedRefreshToken)
    } catch (err) {
      if (isAuthRejection(err)) {
        needsRevalidation.current = false
        clearStoredTokens()
        setAccessToken(null)
        setUser(null)
        setHasAssessment(null)
        return
      }
      needsRevalidation.current = true
      const snapshot = getSessionSnapshot()
      if (snapshot !== null) {
        setAccessToken(getStoredAccessToken() ?? storedAccessToken)
        setUser((current) => current ?? snapshot.user)
        setHasAssessment((current) => current ?? snapshot.hasAssessment)
      }
    }
  }, [applySession])

  useEffect(() => {
    let cancelled = false

    revalidateSession().finally(() => {
      if (!cancelled) {
        setIsInitializing(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [revalidateSession])

  useEffect(() => {
    function retry() {
      if (needsRevalidation.current && navigator.onLine !== false) {
        void revalidateSession()
      }
    }
    function onVisibility() {
      if (document.visibilityState === 'visible') {
        retry()
      }
    }
    window.addEventListener('online', retry)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('online', retry)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [revalidateSession])

  const login = useCallback(
    async (username: string, password: string) => {
      const tokens = await authApi.login(username, password)
      await applySession(tokens.access_token, tokens.refresh_token)
    },
    [applySession],
  )

  const logout = useCallback(() => {
    const refreshToken = getStoredRefreshToken()
    // Best-effort: the tokens are forgotten here either way.
    void (async () => {
      const pushEndpoint = await dropLocalPushSubscription().catch(() => null)
      if (refreshToken !== null) {
        await authApi.logout(refreshToken, pushEndpoint).catch(() => undefined)
      }
    })()
    needsRevalidation.current = false
    clearApiCache()
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
      needsRevalidation.current = false
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

  // Once per signed-in player, not on every token refresh.
  const userId = user?.id ?? null
  useEffect(() => {
    if (userId === null || accessToken === null) {
      return
    }
    resyncPushSubscription(accessToken).catch(() => {
      // Best-effort: Settings still lets the player turn pushes on again.
    })
  }, [userId])

  const adoptTokens = useCallback((nextAccessToken: string, nextRefreshToken: string) => {
    persistTokens(nextAccessToken, nextRefreshToken)
    setAccessToken(nextAccessToken)
  }, [])

  const markAssessmentComplete = useCallback(() => {
    setHasAssessment(true)
    const snapshot = getSessionSnapshot()
    if (snapshot !== null) {
      persistSessionSnapshot({ ...snapshot, hasAssessment: true })
    }
  }, [])

  const updateUser = useCallback((nextUser: UserRead) => {
    setUser(nextUser)
    const snapshot = getSessionSnapshot()
    persistSessionSnapshot({ user: nextUser, hasAssessment: snapshot?.hasAssessment ?? true })
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
      adoptTokens,
      markAssessmentComplete,
      updateUser,
    }),
    [accessToken, user, hasAssessment, isInitializing, login, logout, adoptTokens, markAssessmentComplete, updateUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
