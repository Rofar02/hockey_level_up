import { Navigate, Outlet } from 'react-router-dom'
import { BottomNav } from './BottomNav'
import { AppLoadingScreen } from './ui/AppLoadingScreen'
import { useAuth } from '../hooks/useAuth'

// A layout route (rendered once via App.tsx's <Route element={<ProtectedRoute />}>
// wrapping every protected page as a child route, matched through <Outlet/>)
// -- not a per-page wrapper taking `children` like it used to be. That
// shape looked equivalent but wasn't: React Router gives each top-level
// <Route>'s `element` its own JSX tree, so wrapping every single protected
// page in its own <ProtectedRoute>{page}</ProtectedRoute> meant this
// component (BottomNav included) fully unmounted and remounted on *every*
// navigation between protected pages, not just on login/logout. Most of the
// time that's an invisible no-op remount, but it's a real, avoidable
// full teardown-and-rebuild of BottomNav's own state (e.g. the "Ещё" popup
// closing) landing in the exact same paint as the new page's first render --
// a plausible source of the bottom-nav visual jump reported when opening
// Справочник from that popup specifically (Modal backdrop unmounting +
// BottomNav remounting + new page mounting, all at once). The Outlet
// pattern keeps this component -- and BottomNav -- mounted continuously
// across every protected-page navigation; only the <Outlet/> content
// underneath it swaps.
export function ProtectedRoute() {
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
      <div className="pb-16">
        <Outlet />
      </div>
      <BottomNav />
    </>
  )
}
