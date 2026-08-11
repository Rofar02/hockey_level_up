import type { ReactNode } from 'react'

// Shared underline-tab button -- used by any page-level tab bar (Teams
// list, team detail). Optional `badge` shows a small pill count (e.g.
// pending join requests), hidden when 0/undefined.
export function TabButton({
  active,
  onClick,
  badge,
  children,
}: {
  active: boolean
  onClick: () => void
  badge?: number
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex flex-1 items-center justify-center gap-1.5 border-b-2 px-2 py-2.5 text-sm font-medium transition-colors ${
        active ? 'border-accent-persimmon text-[#F5F7FA]' : 'border-transparent text-[#8A94A6] hover:text-[#F5F7FA]'
      }`}
    >
      {children}
      {badge !== undefined && badge > 0 && (
        <span className="rounded-full bg-accent-persimmon px-1.5 py-0.5 text-[10px] font-semibold leading-none text-dark-bg">
          {badge}
        </span>
      )}
    </button>
  )
}
