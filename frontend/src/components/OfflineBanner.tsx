import { useOnline } from '../hooks/useNetworkStatus'

// "Нет связи" pill at the top of every screen while the server can't be
// reached (Б0, 2026-10-13). Doesn't block anything: the app keeps working on
// what it already has; buttons that truly need the network say so themselves
// (NeedsNetworkHint).
export function OfflineBanner() {
  const online = useOnline()
  if (online) {
    return null
  }
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 top-[calc(env(safe-area-inset-top,0px)+6px)] z-[70] flex justify-center px-4"
    >
      <div className="flex items-center gap-2 rounded-full border border-accent-persimmon/40 bg-dark-card/95 px-3 py-1.5 text-xs font-medium text-text-primary shadow-lg backdrop-blur">
        <i className="ti ti-wifi-off text-sm text-accent-persimmon" aria-hidden="true" />
        Нет связи
      </div>
    </div>
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
