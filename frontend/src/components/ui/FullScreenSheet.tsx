import { useEffect, useId, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { lockBodyScroll, unlockBodyScroll } from '../../utils/bodyScrollLock'
import { useSuppressCoachmarks } from '../../hooks/useSuppressCoachmarks'

interface FullScreenSheetProps {
  title: string
  onClose: () => void
  children: ReactNode
}

// Same contract as Modal (title bar with "Закрыть", scrolling body, body
// scroll locked, coachmarks suppressed), but covering the whole screen --
// for content that needs the room, like a training plan whose rink schemes
// are the point. Portaled to <body> so the floating tab bar (z-40) stays
// underneath.
export function FullScreenSheet({ title, onClose, children }: FullScreenSheetProps) {
  useEffect(() => {
    lockBodyScroll()
    return unlockBodyScroll
  }, [])
  useSuppressCoachmarks(true)
  const titleId = useId()

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      className="fixed inset-0 z-50 flex flex-col bg-dark-bg"
    >
      <div className="flex shrink-0 items-center justify-between gap-4 border-b border-white/5 px-4 pb-2 pt-[calc(0.5rem+env(safe-area-inset-top,0px))]">
        <h2 id={titleId} className="min-w-0 truncate text-lg font-semibold text-text-primary">
          {title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Закрыть"
          className="-mr-2 flex h-11 w-11 shrink-0 items-center justify-center text-text-secondary transition-colors hover:text-text-primary"
        >
          <i className="ti ti-x text-xl" aria-hidden="true" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto w-full max-w-2xl px-4 pb-[calc(1.5rem+env(safe-area-inset-bottom,0px))] pt-4">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
