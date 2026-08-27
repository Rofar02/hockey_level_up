import { useEffect, type ReactNode } from 'react'
import { lockBodyScroll, unlockBodyScroll } from '../../utils/bodyScrollLock'

interface ModalProps {
  title: string
  onClose: () => void
  children: ReactNode
}

// Backdrop click and the close button both call onClose; stopPropagation on
// the card itself keeps a click inside the modal from bubbling up to the
// backdrop and closing it.
//
// The card is a column with a sticky title bar and a separately scrolling
// body -- long content (e.g. TrainingSessionPage's per-set logger) scrolls
// under a close button that's always reachable, instead of the whole card
// (title included) scrolling as one block. `dvh` (not `vh`) for the max
// height so it tracks the *actual* visible viewport on mobile as the
// address bar/keyboard show or hide, rather than the largest-ever one.
export function Modal({ title, onClose, children }: ModalProps) {
  useEffect(() => {
    lockBodyScroll()
    return unlockBodyScroll
  }, [])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85dvh] w-full max-w-md flex-col overflow-hidden rounded-md border border-white/10 bg-dark-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between gap-4 border-b border-white/5 px-6 py-4">
          <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="text-text-secondary transition-colors hover:text-text-primary"
          >
            <i className="ti ti-x text-xl" aria-hidden="true" />
          </button>
        </div>
        <div className="overflow-y-auto p-6">{children}</div>
      </div>
    </div>
  )
}
