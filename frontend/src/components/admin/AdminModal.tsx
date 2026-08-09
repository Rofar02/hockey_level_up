import type { ReactNode } from 'react'

// Same overlay/backdrop-click convention as the shared ui/Modal, but wider
// (admin forms have far more fields than anything user-facing) -- kept
// separate instead of adding a width prop to ui/Modal so this section can
// evolve without touching a component used across the whole app.
export function AdminModal({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 py-8"
      onClick={onClose}
    >
      <div
        className="flex w-full max-w-2xl flex-col overflow-hidden rounded-md border border-white/10 bg-dark-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between gap-4 border-b border-white/10 px-6 py-4">
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
        <div className="flex flex-col gap-6 p-6">{children}</div>
      </div>
    </div>
  )
}
