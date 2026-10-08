// A home-screen app on iOS can sit in memory for days: index.html is never
// reloaded, so the player keeps running the old JS after a deploy until a
// lazy chunk happens to fail (staleChunkReload.ts). On a return from the
// background this asks the server which build it serves (/version.json,
// written by vite.config.ts) and reloads when it differs -- or when the app
// was away so long that a fresh start is better anyway.
import { reloadForStaleChunk } from './staleChunkReload.ts'

// Shorter background stays aren't worth a request.
const CHECK_AFTER_HIDDEN_MS = 2 * 60 * 1000
// After this long in the background reload even on the same build.
const RELOAD_AFTER_HIDDEN_MS = 6 * 60 * 60 * 1000

// Screens where a reload would lose the player's work (a running workout,
// a half-typed coach message, an admin form).
const PROTECTED_PATHS = [/^\/training\//, /^\/coach(\/|$)/, /^\/admin\//]

const NON_TEXT_INPUT_TYPES = new Set(['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file', 'image'])

function isTyping(): boolean {
  const element = document.activeElement
  if (!(element instanceof HTMLElement)) {
    return false
  }
  if (element.isContentEditable || element instanceof HTMLTextAreaElement) {
    return true
  }
  return element instanceof HTMLInputElement && !NON_TEXT_INPUT_TYPES.has(element.type)
}

function canReloadNow(): boolean {
  const path = window.location.pathname
  return !PROTECTED_PATHS.some((pattern) => pattern.test(path)) && !isTyping()
}

async function fetchServerBuild(): Promise<string | null> {
  try {
    const response = await fetch(`/version.json?t=${Date.now()}`, { cache: 'no-store' })
    if (!response.ok) {
      return null
    }
    const data: unknown = await response.json()
    if (typeof data === 'object' && data !== null && typeof (data as { build?: unknown }).build === 'string') {
      return (data as { build: string }).build
    }
  } catch {
    // Offline, or nginx answered with index.html (no version.json yet).
  }
  return null
}

export function installAppUpdateCheck() {
  if (import.meta.env.DEV) {
    return
  }
  let hiddenAt: number | null = null
  // Set when a reload was due but the player was busy -- retried on the
  // next return from the background.
  let pendingReload = false

  const onVisible = async (hiddenFor: number) => {
    let shouldReload = pendingReload || hiddenFor >= RELOAD_AFTER_HIDDEN_MS
    if (!shouldReload) {
      const serverBuild = await fetchServerBuild()
      shouldReload = serverBuild !== null && serverBuild !== __APP_BUILD_ID__
    }
    if (!shouldReload) {
      return
    }
    if (canReloadNow()) {
      reloadForStaleChunk()
    } else {
      pendingReload = true
    }
  }

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      hiddenAt = Date.now()
      return
    }
    if (hiddenAt === null) {
      return
    }
    const hiddenFor = Date.now() - hiddenAt
    hiddenAt = null
    if (pendingReload || hiddenFor >= CHECK_AFTER_HIDDEN_MS) {
      void onVisible(hiddenFor)
    }
  })
}
