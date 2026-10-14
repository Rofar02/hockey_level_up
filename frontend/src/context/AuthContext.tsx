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
import { setOfflineUser } from '../utils/offlineData'
import { clearSaved } from '../utils/offlineStore'
import { discardQueue } from '../utils/writeQueue'
import type { AuthContextValue } from './authContext'

// Signed out (or the server ended the session): nothing of this player's
// stays on the device for the next one to see.
function forgetOfflineData() {
  setOfflineUser(null)
  void clearSaved()
}

// Review 14.10 (3): at start, the server gets this long to confirm the
// session; a slow network (one bar, a captive portal) then opens the app on
// the saved snapshot while the check finishes in the background.
const SESSION_CHECK_WAIT_MS = 4000

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
    setOfflineUser(currentUser.id)
    needsRevalidation.current = false
    setAccessToken(storedAccessToken)
    setUser(currentUser)
    setHasAssessment(status.has_assessment)
    // Б0: ask the browser not to evict the offline copy (the cached app, the
    // saved data and the queued workout) when the phone runs low on space.
    void navigator.storage?.persist?.().catch(() => false)
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
    // Saved screens (Б1) are keyed by player -- known from the snapshot
    // even before the server answers.
    setOfflineUser(getSessionSnapshot()?.user.id ?? null)

    function onSnapshot() {
      const snapshot = getSessionSnapshot()
      if (snapshot !== null) {
        setAccessToken(getStoredAccessToken() ?? storedAccessToken)
        setUser((current) => current ?? snapshot.user)
        setHasAssessment((current) => current ?? snapshot.hasAssessment)
      }
    }

    function onFailure(err: unknown) {
      if (isAuthRejection(err)) {
        needsRevalidation.current = false
        forgetOfflineData()
        clearStoredTokens()
        setAccessToken(null)
        setUser(null)
        setHasAssessment(null)
        return
      }
      needsRevalidation.current = true
      onSnapshot()
    }

    const live = applySession(storedAccessToken, storedRefreshToken)
    let timer: ReturnType<typeof setTimeout> | undefined
    const slow = new Promise<'slow'>((resolve) => {
      timer = setTimeout(() => resolve('slow'), SESSION_CHECK_WAIT_MS)
    })
    const liveDone = live.then(() => 'done' as const)
    // A late failure is handled below (live.catch) -- not an unhandled rejection.
    liveDone.catch(() => undefined)
    try {
      const outcome = getSessionSnapshot() !== null ? await Promise.race([liveDone, slow]) : await live
      if (outcome === 'slow') {
        // The live check keeps going; it commits the fresh state itself, or
        // signs out if the server turns the session down.
        onSnapshot()
        live.catch(onFailure)
      }
    } catch (err) {
      onFailure(err)
    } finally {
      clearTimeout(timer)
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
    // Signing out on purpose drops this player's unsent workout actions (the
    // account page asks first). An expired session keeps them: the same
    // player signs back in and they go.
    const userId = getSessionSnapshot()?.user.id
    if (userId !== undefined) {
      void discardQueue(userId)
    }
    // Best-effort: the tokens are forgotten here either way.
    void (async () => {
      const pushEndpoint = await dropLocalPushSubscription().catch(() => null)
      if (refreshToken !== null) {
        await authApi.logout(refreshToken, pushEndpoint).catch(() => undefined)
      }
    })()
    needsRevalidation.current = false
    clearApiCache()
    forgetOfflineData()
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
      forgetOfflineData()
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
    // Review 14.10 (6): only while signed in, and only over this same
    // player's snapshot -- a late answer must not resurrect a signed-out
    // session or write one account over another's.
    const snapshot = getSessionSnapshot()
    if (getStoredAccessToken() === null || (snapshot !== null && snapshot.user.id !== nextUser.id)) {
      return
    }
    persistSessionSnapshot({ user: nextUser, hasAssessment: snapshot?.hasAssessment ?? true })
  }, [])

  // Review 14.10 (6): signed out, or into another account, in another tab --
  // this one follows instead of mixing two players' data.
  const currentUserId = useRef<string | null>(null)
  useEffect(() => {
    currentUserId.current = user?.id ?? null
  }, [user])
  useEffect(() => {
    function onStorage(event: StorageEvent) {
      if (event.storageArea !== localStorage) {
        return
      }
      if (getStoredAccessToken() === null) {
        if (currentUserId.current !== null) {
          needsRevalidation.current = false
          clearApiCache()
          setAccessToken(null)
          setUser(null)
          setHasAssessment(null)
        }
        return
      }
      const storedUserId = getSessionSnapshot()?.user.id ?? null
      if (storedUserId !== null && storedUserId !== currentUserId.current) {
        clearApiCache()
        setUser(null)
        void revalidateSession()
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [revalidateSession])

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
