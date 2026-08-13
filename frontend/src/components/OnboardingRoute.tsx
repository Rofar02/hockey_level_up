import type { ReactNode } from 'react'
import { useRef } from 'react'
import { Navigate } from 'react-router-dom'
import { AppLoadingScreen } from './ui/AppLoadingScreen'
import { useAuth } from '../hooks/useAuth'

/**
 * Guards /onboarding itself: not logged in -> /login; already completed
 * (has_assessment=true) -> / -- prevents re-running onboarding and
 * silently overwriting equipment/skill choices via a stale bookmark/back
 * button.
 *
 * The "already completed" check is a one-time snapshot, deliberately not
 * reactive to later changes of `hasAssessment`. The flow's own steps live
 * inside this component's children for several renders before
 * hasAssessment flips to true (see SkillsStep) -- if this check re-read
 * the live context value, that flip would redirect a user still mid-flow
 * straight to `/`, skipping whatever step hasn't rendered yet.
 *
 * The snapshot is captured on the first render *after* auth
 * initialization resolves, not simply "at mount" -- on a hard reload this
 * component can mount while isInitializing is still true and
 * hasAssessment is still null (localStorage restore hasn't resolved yet);
 * capturing right then would freeze in a stale `null` and let a
 * since-restored true value get ignored.
 */
export function OnboardingRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, hasAssessment, isInitializing } = useAuth()
  const snapshot = useRef<boolean | null>(null)
  const hasCapturedSnapshot = useRef(false)

  if (!hasCapturedSnapshot.current && !isInitializing) {
    snapshot.current = hasAssessment
    hasCapturedSnapshot.current = true
  }

  if (isInitializing) {
    return <AppLoadingScreen />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (snapshot.current === true) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
