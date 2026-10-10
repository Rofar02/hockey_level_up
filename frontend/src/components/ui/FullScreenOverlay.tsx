import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useSuppressCoachmarks } from '../../hooks/useSuppressCoachmarks'
import { lockBodyScroll, unlockBodyScroll } from '../../utils/bodyScrollLock'

// A screen over the whole app -- the workout finish screen, the report
// reward, the welcome tour (2026-10-08). Portaled to <body> and the app's
// scroller locked while it's up: rendered inside #root (the app's own
// scroll container since the app-shell fix) it started wherever the page
// below was scrolled to, and a swipe on it scrolled the page underneath.
// Its own content scrolls inside it, from the top, without chaining out.
export function FullScreenOverlay({ className = '', children }: { className?: string; children: ReactNode }) {
  useEffect(() => {
    lockBodyScroll()
    return unlockBodyScroll
  }, [])
  useSuppressCoachmarks(true)

  return createPortal(
    <div className={`fixed inset-0 z-50 overscroll-none ${className}`}>{children}</div>,
    document.body,
  )
}
