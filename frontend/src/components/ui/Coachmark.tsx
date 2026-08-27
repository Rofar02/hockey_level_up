import { useCoachmark } from '../../hooks/useCoachmark'

// Reusable "first time on this screen" hint -- a dismissible inline banner,
// not a one-off bit of copy hardcoded into a single page. Any screen that
// wants a coachmark just renders <Coachmark id="..." text="..." />; the id
// is the only thing that has to be unique. An inline banner (not a
// floating tooltip anchored to a specific element) is the deliberately
// simpler shape: no target-ref/position math to get wrong on a phone, and
// it composes with this app's existing card-in-a-vertical-stack layout
// instead of needing to be layered on top of it.
export function Coachmark({ id, icon = 'ti-bulb', text }: { id: string; icon?: string; text: string }) {
  const { shouldShow, dismiss } = useCoachmark(id)

  if (!shouldShow) {
    return null
  }

  return (
    <div className="flex items-start gap-3 rounded-md border-t border-accent-ice/40 bg-accent-ice/[0.08] p-3">
      <i className={`ti ${icon} mt-0.5 shrink-0 text-base text-accent-ice`} aria-hidden="true" />
      <p className="min-w-0 flex-1 text-xs leading-relaxed text-[#F5F7FA]">{text}</p>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Понятно, скрыть подсказку"
        className="shrink-0 text-text-secondary transition-colors hover:text-text-primary"
      >
        <i className="ti ti-x text-base" aria-hidden="true" />
      </button>
    </div>
  )
}
