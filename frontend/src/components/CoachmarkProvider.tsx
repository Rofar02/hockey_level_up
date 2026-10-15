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
  // Non-empty while any useSuppressCoachmarks caller is active -- see that
  // hook and CoachmarkContextValue.setSuppressed for why.
  const [suppressedBy, setSuppressedBy] = useState<Set<string>>(new Set())

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

  const setSuppressed = useCallback((id: string, suppressed: boolean) => {
    setSuppressedBy((previous) => {
      const next = new Set(previous)
      if (suppressed) {
        next.add(id)
      } else {
        next.delete(id)
      }
      return next
    })
  }, [])

  const contextValue = useMemo(
    () => ({ registerStep, unregisterStep, setSuppressed }),
    [registerStep, unregisterStep, setSuppressed],
  )

  const unseenSteps = seenIds !== null ? steps.filter((step) => !seenIds.has(step.hintId)) : []
  const activeStep = suppressedBy.size === 0 ? (unseenSteps[0] ?? null) : null

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
// Below this much room on either side of the target the card goes to the
// middle of the screen instead -- a card squeezed to a sliver (or to 0, the
// 15.10 blocker: a tall target left no room, maxHeight hit 0, the card
// vanished while the backdrop kept swallowing every tap) is worse than one
// that covers part of the target.
const MIN_TOOLTIP_ROOM = 140

interface OverlayLayout {
  // null: the target can't be pointed at right now (detached, display:none,
  // zero size) -- the card is centred.
  rect: DOMRect | null
  bottomNavHeight: number
  viewportHeight: number
}

function usableRect(target: HTMLElement): DOMRect | null {
  if (!target.isConnected) {
    return null
  }
  const rect = target.getBoundingClientRect()
  return rect.width > 0 && rect.height > 0 ? rect : null
}

function bottomNavHeightNow(): number {
  const nav = document.querySelector<HTMLElement>('[data-app-bottom-nav]')
  if (nav === null || nav.dataset.navState === 'hidden') {
    return 0
  }
  return nav.getBoundingClientRect().height
}

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
  const [layout, setLayout] = useState<OverlayLayout | null>(null)
  // Fades the whole overlay in instead of it snapping to full darkness the
  // instant the layout resolves -- found live-testing, 2026-08-30 ("надо
  // чтобы плавно показывалось, а то сейчас он сам экран как будто
  // переводит").
  const [entered, setEntered] = useState(false)

  // Re-measured for as long as the hint is up, not just while the first
  // scroll settles (15.10): a page that is still loading (a card appearing
  // above the target, images, the week arriving) moves the target long
  // after the first half-second. Every layout change also brings the target
  // back into view if it slid out.
  useLayoutEffect(() => {
    let frame = 0
    function measure() {
      setLayout({
        rect: usableRect(target),
        bottomNavHeight: bottomNavHeightNow(),
        viewportHeight: window.innerHeight,
      })
    }
    function scheduleMeasure() {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(measure)
    }
    function bringIntoView() {
      const rect = usableRect(target)
      if (rect === null) {
        return
      }
      const bandTop = TOP_BOTTOM_SAFE_MARGIN
      const bandBottom = window.innerHeight - bottomNavHeightNow() - TOP_BOTTOM_SAFE_MARGIN
      if (rect.top >= bandTop && rect.bottom <= bandBottom) {
        return
      }
      // A target taller than the band: its top edge, so the card can sit
      // under the part that's visible. Otherwise as little scrolling as it
      // takes ('nearest' -- the hint is about the current screen).
      const tall = rect.height > bandBottom - bandTop
      target.scrollIntoView({ behavior: 'smooth', block: tall ? 'start' : 'nearest' })
    }
    measure()
    bringIntoView()
    const enterFrame = requestAnimationFrame(() => setEntered(true))
    // scrollIntoView animates -- re-measure as it settles.
    const timers = [50, 150, 300, 500, 1000].map((delay) => setTimeout(measure, delay))
    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => {
            bringIntoView()
            scheduleMeasure()
          })
    observer?.observe(target)
    observer?.observe(document.body)
    const nav = document.querySelector('[data-app-bottom-nav]')
    if (nav !== null) {
      observer?.observe(nav)
    }
    window.addEventListener('resize', scheduleMeasure)
    window.visualViewport?.addEventListener('resize', scheduleMeasure)
    // capture: true -- a scroll inside a nested scroll container (e.g. a
    // long exercise list) doesn't bubble to window otherwise.
    window.addEventListener('scroll', scheduleMeasure, true)
    return () => {
      cancelAnimationFrame(frame)
      cancelAnimationFrame(enterFrame)
      timers.forEach(clearTimeout)
      observer?.disconnect()
      window.removeEventListener('resize', scheduleMeasure)
      window.visualViewport?.removeEventListener('resize', scheduleMeasure)
      window.removeEventListener('scroll', scheduleMeasure, true)
    }
  }, [target])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onAdvance()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onAdvance])

  if (layout === null) {
    return null
  }

  const { bottomNavHeight, viewportHeight } = layout
  // The usable band excludes BottomNav's real footprint and a small top
  // margin -- the card never lands on the nav bar.
  const safeBottom = viewportHeight - bottomNavHeight - TOP_BOTTOM_SAFE_MARGIN
  const safeTop = TOP_BOTTOM_SAFE_MARGIN
  // Still off screen (mid-scroll, or the page can't scroll that far) =
  // nothing to point at yet.
  const rect =
    layout.rect !== null && layout.rect.bottom > safeTop && layout.rect.top < viewportHeight - bottomNavHeight
      ? layout.rect
      : null
  const spaceBelow = rect !== null ? safeBottom - (rect.bottom + SPOTLIGHT_PADDING + TOOLTIP_GAP) : 0
  const spaceAbove = rect !== null ? rect.top - SPOTLIGHT_PADDING - TOOLTIP_GAP - safeTop : 0
  const placement: 'below' | 'above' | 'center' =
    rect === null || Math.max(spaceBelow, spaceAbove) < MIN_TOOLTIP_ROOM
      ? 'center'
      : spaceBelow >= spaceAbove
        ? 'below'
        : 'above'
  const tooltipStyle =
    placement === 'below' && rect !== null
      ? { top: rect.bottom + SPOTLIGHT_PADDING + TOOLTIP_GAP, maxHeight: spaceBelow }
      : placement === 'above' && rect !== null
        ? { bottom: viewportHeight - rect.top + SPOTLIGHT_PADDING + TOOLTIP_GAP, maxHeight: spaceAbove }
        : {
            top: '50%',
            transform: 'translateY(-50%)',
            maxHeight: Math.max(safeBottom - safeTop, MIN_TOOLTIP_ROOM),
          }
  const isLast = totalUnseen <= 1

  return createPortal(
    <div
      data-coachmark-overlay
      data-coachmark-placement={placement}
      className={`fixed inset-x-0 top-0 z-[100] overflow-hidden transition-opacity duration-300 ease-out ${
        entered ? 'opacity-100' : 'opacity-0'
      }`}
      // Stops above BottomNav: the nav stays visible and tappable while a
      // hint is up -- a hint never traps the player on a screen.
      style={{ bottom: bottomNavHeight }}
      // A tap on the dimmed page closes the hint (marks it seen) -- the tap
      // itself never reaches the page underneath.
      onClick={(event) => {
        event.stopPropagation()
        onAdvance()
      }}
      role="presentation"
    >
      {rect !== null ? (
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
      ) : (
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[rgba(6,10,18,0.86)]" />
      )}
      <div
        role="dialog"
        aria-label="Подсказка"
        className="fixed inset-x-4 flex flex-col gap-3 overflow-y-auto rounded-md border-t border-accent-ice/40 bg-dark-card p-4 shadow-xl transition-all duration-200 ease-out"
        style={tooltipStyle}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <i className={`ti ${icon} mt-0.5 shrink-0 text-lg text-accent-ice`} aria-hidden="true" />
          <p className="min-w-0 flex-1 text-sm leading-relaxed text-[#F5F7FA]">{text}</p>
        </div>
        <div className="flex items-center justify-between gap-3">
          {!isLast ? <span className="text-xs text-text-secondary">Шаг 1 из {totalUnseen}</span> : <span />}
          <Button onClick={onAdvance} className="shrink-0 px-4 py-1.5 text-sm">
            {isLast ? 'Понятно' : 'Далее'}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
