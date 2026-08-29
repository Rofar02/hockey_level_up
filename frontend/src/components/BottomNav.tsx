import { NavLink } from 'react-router-dom'

const TABS: { to: string; icon: string; label: string; end?: boolean }[] = [
  { to: '/', icon: 'ti-home', label: 'Главная', end: true },
  { to: '/schedule/new', icon: 'ti-calendar', label: 'Неделя' },
  { to: '/profile', icon: 'ti-user', label: 'Профиль' },
  // Its own route (/more, see MorePage) rather than a popup opened in place
  // -- a plain NavLink like the other three tabs, so it's reachable by
  // back/forward and a direct link, not just a tap on this button.
  { to: '/more', icon: 'ti-dots', label: 'Ещё' },
]

export function BottomNav() {
  return (
    <nav
      // Queried by CoachmarkOverlay to reserve exactly this much space at
      // the bottom of the viewport, rather than guessing a pixel constant --
      // see that component's own comment for why (2026-08-30: a tooltip
      // placed "below" a spotlighted element could land right on top of
      // this nav on a short phone screen).
      data-app-bottom-nav
      className="fixed inset-x-0 bottom-0 z-40 border-t border-white/5 bg-dark-card"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <div className="mx-auto flex max-w-2xl items-stretch justify-around">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-1 py-2.5 text-xs font-medium transition-colors ${
                isActive ? 'text-accent-ice' : 'text-text-secondary hover:text-text-primary'
              }`
            }
          >
            <i className={`ti ${tab.icon} text-xl`} aria-hidden="true" />
            {tab.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
