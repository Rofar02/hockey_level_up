import { createPortal } from 'react-dom'
import { useSyncExternalStore } from 'react'
import { useOnline } from '../hooks/useNetworkStatus'
import { usePendingWrites } from '../hooks/useWriteQueue'
import { getOldestShownAt, subscribeSavedDataAge } from '../utils/offlineData'

function formatShownAt(storedAt: number): string {
  const shown = new Date(storedAt)
  const time = shown.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  const today = new Date()
  if (shown.toDateString() === today.toDateString()) {
    return time
  }
  return `${shown.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}, ${time}`
}

// "Нет связи" pill at the top of every screen while the server can't be
// reached (Б0, 2026-10-13). Doesn't block anything: the app keeps working on
// what it already has; buttons that truly need the network say so themselves
// (NeedsNetworkHint).
export function OfflineBanner() {
  const online = useOnline()
  // Б1: when saved answers are on screen, how old the oldest one is.
  const shownAt = useSyncExternalStore(subscribeSavedDataAge, getOldestShownAt, () => null)
  // Б2: workout writes waiting to be sent.
  const pending = usePendingWrites()
  if (online) {
    return null
  }
  // Portaled to <body> like FullScreenOverlay, so it stays on top of the
  // workout player and the finish screen too.
  return createPortal(
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 top-[calc(env(safe-area-inset-top,0px)+6px)] z-[70] flex justify-center px-4"
    >
      <div className="flex items-center gap-2 rounded-full border border-accent-persimmon/40 bg-dark-card/95 px-3 py-1.5 text-xs font-medium text-text-primary shadow-lg backdrop-blur">
        <i className="ti ti-wifi-off text-sm text-accent-persimmon" aria-hidden="true" />
        Нет связи
        {shownAt !== null && <span className="text-text-secondary">· данные от {formatShownAt(shownAt)}</span>}
        {pending > 0 && <span className="text-text-secondary">· ждут отправки: {pending}</span>}
      </div>
    </div>,
    document.body,

  )
}

// Under a button that can't work offline (coach chat, «Иду», joining a
// team, payment, sign-in): the button itself goes disabled, this says why.
export function NeedsNetworkHint({ className = '' }: { className?: string }) {
  const online = useOnline()
  if (online) {
    return null
  }
  return (
    <p className={`flex items-center gap-1.5 text-xs text-text-secondary ${className}`}>
      <i className="ti ti-wifi-off" aria-hidden="true" />
      Нужна связь
    </p>
  )
}
