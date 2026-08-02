import { createContext } from 'react'
import type { UserRead } from '../types/user'

export interface AuthContextValue {
  accessToken: string | null
  user: UserRead | null
  // null only while unauthenticated -- login() always resolves it to a
  // real boolean before it settles, so any authenticated screen can treat
  // it as a plain boolean.
  hasAssessment: boolean | null
  isAuthenticated: boolean
  // True until the localStorage-restore attempt on first load resolves.
  // Route guards must wait for this before redirecting on isAuthenticated,
  // otherwise a reload always looks logged-out for the first render.
  isInitializing: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  markAssessmentComplete: () => void
  updateUser: (user: UserRead) => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
