// The last few screens the player opened (2026-10-04) -- attached to a
// feedback message, so a bug report says where the player came from rather
// than just "/feedback". In memory only, never persisted.
const MAX_ROUTES = 5
const routes: string[] = []

export function recordRoute(pathname: string): void {
  if (routes[routes.length - 1] === pathname) {
    return
  }
  routes.push(pathname)
  if (routes.length > MAX_ROUTES) {
    routes.shift()
  }
}

export function recentRoutes(): string {
  return routes.join(' → ')
}
