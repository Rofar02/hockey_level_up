import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

// Guards /admin/*: not logged in -> /login (same as ProtectedRoute); logged
// in but not an admin -> / (no separate "forbidden" page -- regular users
// should see no trace of this section existing at all, not even a 403).
//
// Deliberately doesn't render BottomNav like ProtectedRoute does -- this is
// an internal content-authoring tool, not a screen in the player-facing app
// shell.
export function AdminRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isInitializing, user } = useAuth()

  if (isInitializing) {
    return (
      <div className="flex min-h-svh items-center justify-center bg-dark-bg">
        <p className="text-sm text-text-secondary">Загрузка...</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (user?.is_admin !== true) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
