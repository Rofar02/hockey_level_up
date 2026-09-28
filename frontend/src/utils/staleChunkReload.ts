// Every page is a lazy chunk with a content hash in its name. A deploy
// replaces them, so a tab opened before the deploy asks for chunk files that
// no longer exist the next time it navigates -- nginx answers with
// index.html, the import fails, and without this the screen just went blank
// until the player reloaded by hand (found 2026-09-28). One automatic reload
// picks up the new index.html and its new chunk names.

const RELOAD_KEY = 'icelevel.staleChunkReloadAt'
// A second failure within this window means reloading didn't help (a real
// outage, not a stale tab) -- stop and let AppErrorBoundary show its screen
// instead of reloading forever.
const RELOAD_GUARD_MS = 10_000

export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i.test(
    message,
  )
}

// Returns false when a reload already happened moments ago.
export function reloadForStaleChunk(): boolean {
  let lastReloadAt = 0
  try {
    lastReloadAt = Number(sessionStorage.getItem(RELOAD_KEY) ?? 0)
  } catch {
    // Storage blocked -- still reload once; worst case the boundary shows.
  }
  if (Date.now() - lastReloadAt < RELOAD_GUARD_MS) {
    return false
  }
  try {
    sessionStorage.setItem(RELOAD_KEY, String(Date.now()))
  } catch {
    // Same as above.
  }
  window.location.reload()
  return true
}

export function installStaleChunkReload() {
  // Vite emits this when a lazy import (or the CSS it preloads) fails.
  window.addEventListener('vite:preloadError', (event) => {
    if (reloadForStaleChunk()) {
      event.preventDefault()
    }
  })
}
