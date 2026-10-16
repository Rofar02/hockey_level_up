import { createContext } from 'react'

export interface CoachmarkStepInfo {
  hintId: string
  text: string
  icon: string
}

export interface CoachmarkContextValue {
  // Called from useCoachmarkStep's ref callback as its target element
  // mounts/unmounts -- CoachmarkProvider tracks whichever steps are
  // currently registered (i.e. currently on screen) and shows the first
  // unseen one, in registration order.
  registerStep: (step: CoachmarkStepInfo, element: HTMLElement) => void
  unregisterStep: (hintId: string) => void
  // Any full-screen takeover (OnboardingTour, Modal, ...) can hold this
  // while it's up so no coachmark shows behind or on top of it -- a
  // registered target stays mounted (just visually covered) while such an
  // overlay is open, so without this the tour would otherwise render right
  // through/over it (found live, 2026-08-30: a brand-new user's welcome
  // screen showed the "Ближайшие пороги" coachmark bleeding through it,
  // pointing at a card the welcome screen itself was covering). `id` is a
  // caller-owned key (e.g. from useId()) so multiple overlays suppressing
  // at once compose correctly instead of one's cleanup undoing another's.
  setSuppressed: (id: string, suppressed: boolean) => void
  // Marks these hints seen without showing them -- «Пропустить» on the
  // welcome screen turns off the whole first-day tour (15.10).
  dismissHints: (hintIds: readonly string[]) => void
}

// Every hint of the first-day tour (each screen's useCoachmarkStep id).
export const FIRST_DAY_HINTS = [
  'home-skill-milestones',
  'schedule-week-day-tap',
  'profile-stat-unlocks',
  'nav-team-tab',
] as const

// null outside a CoachmarkProvider -- useCoachmarkStep degrades to a no-op
// ref rather than throwing, since a missing tour overlay should never break
// the page it's meant to just be a hint on top of.
export const CoachmarkContext = createContext<CoachmarkContextValue | null>(null)
