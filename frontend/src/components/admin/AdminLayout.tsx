import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/admin/exercises', label: 'Упражнения' },
  { to: '/admin/skills', label: 'Навыки' },
  { to: '/admin/reference-articles', label: 'Справочник' },
]

// Deliberately plain: dark-bg/dark-card/text-* tokens already used
// app-wide, but no IceGlowBackground/rink imagery -- this is an internal
// content tool, not a player-facing screen, so it skips the visual polish
// pass the rest of the app gets.
export function AdminLayout({ title, children }: { title: string; children: ReactNode }) {
  const location = useLocation()

  return (
    <div className="min-h-svh bg-dark-bg text-text-primary">
      <header className="border-b border-white/10 bg-dark-card">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-6">
            <Link to="/admin" className="font-semibold">
              Админ-панель
            </Link>
            <nav className="flex gap-4 text-sm">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`transition-colors hover:text-text-primary ${
                    location.pathname.startsWith(item.to) ? 'text-accent-ice' : 'text-text-secondary'
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <Link to="/" className="text-sm text-text-secondary transition-colors hover:text-text-primary">
            ← В приложение
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        <h1 className="mb-6 text-xl font-semibold">{title}</h1>
        {children}
      </main>
    </div>
  )
}
