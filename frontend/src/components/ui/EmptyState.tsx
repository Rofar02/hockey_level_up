import { CARD_CLASS } from './cardStyle'

// Shared "nothing here yet" placeholder -- previously every empty list
// (friends, teams, training parties, ...) was just a single line of muted
// text floating in an otherwise-bare page. An icon plus a two-line
// title/hint reads as "this is a real, intentional state" rather than
// looking broken or unfinished.
export function EmptyState({ icon, title, hint }: { icon: string; title: string; hint?: string }) {
  return (
    <div className={`flex flex-col items-center gap-3 px-6 py-10 text-center ${CARD_CLASS}`}>
      {/* Circle badge, not a bare floating icon -- same "icon in an accent
          circle" motif as the podium avatar rings and RankBadge elsewhere
          (hockey design pass, 2026-08-30), so an empty state reads as part
          of the same visual system rather than a generic placeholder. */}
      <span className="flex h-14 w-14 items-center justify-center rounded-full bg-accent-ice/10">
        <i className={`ti ${icon} text-2xl text-accent-ice`} aria-hidden="true" />
      </span>
      <div className="flex flex-col gap-1">
        <p className="text-sm text-[#F5F7FA]">{title}</p>
        {hint !== undefined && <p className="text-xs text-[#8A94A6]">{hint}</p>}
      </div>
    </div>
  )
}
