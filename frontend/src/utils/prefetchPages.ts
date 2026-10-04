// Background download of every page's code after login (2026-10-04), so the
// first visit to a tab is instant instead of "blank, then the page". Pages
// are lazy chunks (App.tsx); this asks for the same chunks the router would.
// Runs once, starts after the first screen has painted, and fetches one page
// at a time so it never competes with what the player is doing. Admin pages
// are left out -- most players never open them.
const pageModules = import.meta.glob('../pages/*.tsx')

let started = false

export function prefetchPages(): void {
  if (started) {
    return
  }
  started = true
  const loaders = Object.values(pageModules)
  const next = (index: number) => {
    if (index >= loaders.length) {
      return
    }
    loaders[index]()
      .catch(() => undefined)
      .finally(() => {
        const schedule = window.requestIdleCallback ?? ((cb: () => void) => window.setTimeout(cb, 50))
        schedule(() => next(index + 1))
      })
  }
  next(0)
}
