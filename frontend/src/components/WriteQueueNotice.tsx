import { createPortal } from 'react-dom'
import { useState } from 'react'
import { useFailedWrites } from '../hooks/useWriteQueue'
import { dismissFailed } from '../utils/writeQueue'

function actionsWord(count: number): string {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) {
    return 'действие'
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return 'действия'
  }
  return 'действий'
}

// Б2: workout writes made offline that the server refused once they got
// through (the day was rebuilt, an exercise was replaced) -- said out loud,
// never dropped silently.
export function WriteQueueNotice() {
  const failed = useFailedWrites()
  const [open, setOpen] = useState(false)
  if (failed.length === 0) {
    return null
  }
  const verb = failed.length === 1 ? 'не сохранилось' : 'не сохранились'
  // Portaled to <body> like FullScreenOverlay, so it stays on top of the
  // workout player and the finish screen too.
  return createPortal(
    <div
      role="alert"
      className="fixed inset-x-3 top-[calc(env(safe-area-inset-top,0px)+48px)] z-[70] mx-auto flex max-w-md flex-col gap-2 rounded-xl border border-accent-persimmon/40 bg-dark-card px-4 py-3 text-sm text-text-primary shadow-lg"
    >
      <p className="flex items-start gap-2">
        <i className="ti ti-alert-triangle mt-0.5 text-accent-persimmon" aria-hidden="true" />
        <span className="flex-1">
          {failed.length} {actionsWord(failed.length)} {verb}: тренировка изменилась, пока не было связи.
        </span>
      </p>
      {open && (
        <ul className="flex flex-col gap-1 pl-6 text-xs text-text-secondary">
          {failed.map((item) => (
            <li key={item.key}>
              {item.label} — {item.detail}
            </li>
          ))}
        </ul>
      )}
      <div className="flex justify-end gap-2">
        <button type="button" className="min-h-11 px-3 text-xs text-text-secondary" onClick={() => setOpen((v) => !v)}>
          {open ? 'Скрыть' : 'Подробнее'}
        </button>
        <button type="button" className="min-h-11 px-3 text-xs font-semibold text-accent-ice" onClick={() => void dismissFailed()}>
          Понятно
        </button>
      </div>
    </div>,
    document.body,

  )
}
