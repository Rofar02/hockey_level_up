import type { ReactNode } from 'react'

interface ModalProps {
  title: string
  onClose: () => void
  children: ReactNode
}

// Backdrop click and the close button both call onClose; stopPropagation on
// the card itself keeps a click inside the modal from bubbling up to the
// backdrop and closing it. max-h + overflow-y-auto on the card means long
// content scrolls within the card, not the page behind it.
export function Modal({ title, onClose, children }: ModalProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-md border border-white/10 bg-dark-card p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-4">
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
        {children}
      </div>
    </div>
  )
}
