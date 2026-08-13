import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { BottomNav } from './BottomNav'
import { AppLoadingScreen } from './ui/AppLoadingScreen'
import { useAuth } from '../hooks/useAuth'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, hasAssessment, isInitializing } = useAuth()

  // Hold off on any redirect while a reload is still trying to restore the
  // session from localStorage -- isAuthenticated is false at this point
  // regardless of whether restore will succeed, so redirecting now would
  // bounce an actually-logged-in user to /login for one render.
  if (isInitializing) {
    return <AppLoadingScreen />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (hasAssessment === false) {
    return <Navigate to="/onboarding" replace />
  }

  // pb reserves room so BottomNav (fixed) never overlaps the page's own
  // bottom content -- kept here rather than in each page so every protected
  // screen gets it automatically.
  return (
    <>
      <div className="pb-16">{children}</div>
      <BottomNav />
    </>
  )
}
