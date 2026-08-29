import { useCallback, useContext, useRef } from 'react'
import { CoachmarkContext } from '../context/coachmarkContext'

// Attach the returned ref to whatever element the hint should point at --
// that's the entire integration surface, no per-screen copy-paste of tour
// bookkeeping. `hintId` must be unique app-wide (same requirement as a React
// `key`); it's also what CoachmarkService persists as "seen" server-side, so
// it must stay stable once shipped (renaming it un-dismisses the hint for
// everyone).
export function useCoachmarkStep(hintId: string, text: string, icon = 'ti-hand-click') {
  const context = useContext(CoachmarkContext)
  // Ref, not a dependency array entry -- text/icon can be computed fresh
  // each render (e.g. interpolating a value into the copy) without that
  // forcing the ref callback below to re-run and re-register on every
  // render; only an actual element mount/unmount should do that.
  const stepRef = useRef({ hintId, text, icon })
  stepRef.current = { hintId, text, icon }

  return useCallback(
    (element: HTMLElement | null) => {
      if (context === null) {
        return
      }
      if (element !== null) {
        context.registerStep(stepRef.current, element)
      } else {
        context.unregisterStep(hintId)
      }
    },
    [context, hintId],
  )
}
