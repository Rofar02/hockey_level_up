import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import * as assessmentApi from '../api/assessment'
import * as authApi from '../api/auth'
import { ApiError } from '../api/client'
import type { UserRead } from '../types/user'
import { AuthContext } from './authContext'
import type { AuthContextValue } from './authContext'

const ACCESS_TOKEN_KEY = 'hlu_access_token'
const REFRESH_TOKEN_KEY = 'hlu_refresh_token'

function persistTokens(accessToken: string, refreshToken: string) {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
}

function clearStoredTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

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
      const storedAccessToken = localStorage.getItem(ACCESS_TOKEN_KEY)
      const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
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
