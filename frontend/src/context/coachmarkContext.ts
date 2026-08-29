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
}

// null outside a CoachmarkProvider -- useCoachmarkStep degrades to a no-op
// ref rather than throwing, since a missing tour overlay should never break
// the page it's meant to just be a hint on top of.
export const CoachmarkContext = createContext<CoachmarkContextValue | null>(null)
