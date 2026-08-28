import { CARD_CLASS } from './cardStyle'

// Shared "nothing here yet" placeholder -- previously every empty list
// (friends, teams, training parties, ...) was just a single line of muted
// text floating in an otherwise-bare page. An icon plus a two-line
// title/hint reads as "this is a real, intentional state" rather than
// looking broken or unfinished.
export function EmptyState({ icon, title, hint }: { icon: string; title: string; hint?: string }) {
  return (
    <div className={`flex flex-col items-center gap-3 px-6 py-10 text-center ${CARD_CLASS}`}>
      <i className={`ti ${icon} text-3xl text-[#8A94A6]`} aria-hidden="true" />
      <div className="flex flex-col gap-1">
        <p className="text-sm text-[#F5F7FA]">{title}</p>
        {hint !== undefined && <p className="text-xs text-[#8A94A6]">{hint}</p>}
      </div>
    </div>
  )
}
