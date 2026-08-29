import { useContext, useEffect, useId } from 'react'
import { CoachmarkContext } from '../context/coachmarkContext'

// Call from any full-screen takeover (a welcome/tour screen, a modal) for as
// long as it's covering the page -- see CoachmarkContextValue.setSuppressed
// for why this exists. `active` toggling (not just mount/unmount) is
// supported so a component can hold this hook unconditionally and just flip
// a boolean, the same shape as any other conditional effect.
export function useSuppressCoachmarks(active: boolean) {
  const context = useContext(CoachmarkContext)
  const id = useId()

  useEffect(() => {
    if (context === null || !active) {
      return
    }
    context.setSuppressed(id, true)
    return () => context.setSuppressed(id, false)
  }, [context, id, active])
}
