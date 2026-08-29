import { useCallback, useEffect, useLayoutEffect, useMemo, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Button } from './ui/Button'
import * as usersApi from '../api/users'
import { useAuth } from '../hooks/useAuth'
import { CoachmarkContext } from '../context/coachmarkContext'
import type { CoachmarkStepInfo } from '../context/coachmarkContext'

interface RegisteredStep extends CoachmarkStepInfo {
  element: HTMLElement
}

// App-wide first-touch tour: a dimmed backdrop with a spotlight cutout
// around whatever element a screen registered via useCoachmarkStep, one
// card of copy, "Далее"/"Понятно" to advance -- the "как в топ приложениях"
// walkthrough feel (2026-08-30), replacing the earlier inline-banner
// Coachmark/useCoachmark (localStorage-only, no spotlight, no queue).
// Mounted once inside ProtectedRoute so it persists across page navigation
// and can track whatever the *current* page has registered.
export function CoachmarkProvider({ children }: { children: ReactNode }) {
  const { accessToken } = useAuth()
  // null = not fetched yet -- deliberately distinct from an empty Set, so
  // the overlay never flashes a hint the athlete already dismissed before
  // this load finishes (see unseenSteps below).
  const [seenIds, setSeenIds] = useState<Set<string> | null>(null)
  // Registration order = screen mount order = queue order. Re-registering
  // the same hintId (a re-render passing a new element) replaces its entry
  // in place rather than moving it to the back of the queue.
  const [steps, setSteps] = useState<RegisteredStep[]>([])

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    usersApi
      .getSeenCoachmarks(accessToken)
      .then((ids) => {
        if (!cancelled) {
          setSeenIds(new Set(ids))
        }
      })
      .catch(() => {
        // Best-effort -- treat a failed fetch as "nothing seen yet" rather
        // than never showing the tour at all; worst case a hint that was
        // actually already dismissed shows once more.
        if (!cancelled) {
          setSeenIds(new Set())
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  const registerStep = useCallback((step: CoachmarkStepInfo, element: HTMLElement) => {
    setSteps((previous) => [...previous.filter((s) => s.hintId !== step.hintId), { ...step, element }])
  }, [])

  const unregisterStep = useCallback((hintId: string) => {
    setSteps((previous) => previous.filter((s) => s.hintId !== hintId))
  }, [])

  const contextValue = useMemo(() => ({ registerStep, unregisterStep }), [registerStep, unregisterStep])

  const unseenSteps = seenIds !== null ? steps.filter((step) => !seenIds.has(step.hintId)) : []
  const activeStep = unseenSteps[0] ?? null

  async function handleAdvance() {
    if (activeStep === null) {
      return
    }
    // Optimistic -- the queue must move on immediately regardless of the
    // network; a failed persist just means this one hint can show again on
    // a future visit, same "best-effort, worst case it repeats" tradeoff as
    // the old localStorage version made implicitly.
    setSeenIds((previous) => new Set(previous).add(activeStep.hintId))
    if (accessToken !== null) {
      try {
        await usersApi.markCoachmarkSeen(activeStep.hintId, accessToken)
      } catch {
        // Best-effort, see above.
      }
    }
  }

  return (
    <CoachmarkContext.Provider value={contextValue}>
      {children}
      {activeStep !== null && (
        <CoachmarkOverlay
          key={activeStep.hintId}
          target={activeStep.element}
          text={activeStep.text}
          icon={activeStep.icon}
          totalUnseen={unseenSteps.length}
          onAdvance={handleAdvance}
        />
      )}
    </CoachmarkContext.Provider>
  )
}

const SPOTLIGHT_PADDING = 8
const TOOLTIP_GAP = 12
// Kept clear of the very top of the screen (status bar / notch territory)
// and, combined with the measured BottomNav height, off the nav bar too.
const TOP_BOTTOM_SAFE_MARGIN = 16

function CoachmarkOverlay({
  target,
  text,
  icon,
  totalUnseen,
  onAdvance,
}: {
  target: HTMLElement
  text: string
  icon: string
  totalUnseen: number
  onAdvance: () => void
}) {
  const [rect, setRect] = useState<DOMRect | null>(null)
  // How much of the viewport's bottom edge BottomNav actually occupies --
  // measured, not guessed, so this stays correct regardless of safe-area
  // inset on a given phone. 0 on any screen without it mounted (falls back
  // to no reservation rather than crashing).
  const [bottomNavHeight, setBottomNavHeight] = useState(0)

  useLayoutEffect(() => {
    function measure() {
      setRect(target.getBoundingClientRect())
      const nav = document.querySelector('[data-app-bottom-nav]')
      setBottomNavHeight(nav?.getBoundingClientRect().height ?? 0)
    }
    measure()
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    // scrollIntoView animates -- re-measure a few times as it settles
    // instead of only once before the scroll has actually happened.
    const timers = [50, 150, 300, 500].map((delay) => setTimeout(measure, delay))
    window.addEventListener('resize', measure)
    // capture: true -- a scroll inside a nested scroll container (e.g. a
    // long exercise list) doesn't bubble to window otherwise.
    window.addEventListener('scroll', measure, true)
    return () => {
      timers.forEach(clearTimeout)
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [target])

  if (rect === null) {
    return null
  }

  const viewportHeight = window.innerHeight
  // The usable band excludes BottomNav's real footprint and a small top
  // margin -- without this, a target sitting low on a short phone screen
  // (the exact case found live, 2026-08-30: "маленько не симпатично
  // смотрится" on mobile) could place the tooltip right on top of the nav
  // bar instead of respecting it.
  const safeBottom = viewportHeight - bottomNavHeight - TOP_BOTTOM_SAFE_MARGIN
  const safeTop = TOP_BOTTOM_SAFE_MARGIN
  const spaceBelow = safeBottom - (rect.bottom + SPOTLIGHT_PADDING + TOOLTIP_GAP)
  const spaceAbove = rect.top - SPOTLIGHT_PADDING - TOOLTIP_GAP - safeTop
  const placeBelow = spaceBelow >= spaceAbove

  return createPortal(
    <div
      className="fixed inset-0 z-[100]"
      // Swallow every tap on the dimmed page behind the tour -- same "read
      // it, then tap Далее" intent as a modal backdrop that doesn't
      // dismiss on its own tap (see Modal.tsx's own click-through guard).
      onClick={(event) => event.stopPropagation()}
      role="presentation"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none fixed rounded-lg transition-all duration-200 ease-out"
        style={{
          top: rect.top - SPOTLIGHT_PADDING,
          left: rect.left - SPOTLIGHT_PADDING,
          width: rect.width + SPOTLIGHT_PADDING * 2,
          height: rect.height + SPOTLIGHT_PADDING * 2,
          boxShadow: '0 0 0 9999px rgba(6,10,18,0.86)',
        }}
      />
      <div
        role="tooltip"
        className="fixed inset-x-4 flex flex-col gap-3 overflow-y-auto rounded-md border-t border-accent-ice/40 bg-dark-card p-4 shadow-xl transition-all duration-200 ease-out"
        style={
          placeBelow
            ? {
                top: rect.bottom + SPOTLIGHT_PADDING + TOOLTIP_GAP,
                // Safety net, not the primary layout mechanism -- caps the
                // card at whatever room is actually left above BottomNav so
                // it scrolls internally in the pathological case (very long
                // hint text) instead of ever visually overlapping the nav.
                maxHeight: Math.max(spaceBelow, 0),
              }
            : {
                bottom: viewportHeight - rect.top + SPOTLIGHT_PADDING + TOOLTIP_GAP,
                maxHeight: Math.max(spaceAbove, 0),
              }
        }
      >
        <div className="flex items-start gap-3">
          <i className={`ti ${icon} mt-0.5 shrink-0 text-lg text-accent-ice`} aria-hidden="true" />
          <p className="min-w-0 flex-1 text-sm leading-relaxed text-[#F5F7FA]">{text}</p>
        </div>
        <div className="flex items-center justify-between gap-3">
          {totalUnseen > 1 ? (
            <span className="text-xs text-text-secondary">Шаг 1 из {totalUnseen}</span>
          ) : (
            <span />
          )}
          <Button onClick={onAdvance} className="px-4 py-1.5 text-sm">
            {totalUnseen > 1 ? 'Далее' : 'Понятно'}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
