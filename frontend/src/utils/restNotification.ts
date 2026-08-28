// Local (device-only, no server push) notification for "rest is over" --
// icelevel_player_master_prompt.md, 2026-08-28. Honest limitation, stated
// up front: this is a web PWA, not a Capacitor/native-wrapped app, so there
// is no UNUserNotificationCenter/AlarmManager here -- the browser's own JS
// timer is what schedules this, and mobile OSes are free to fully suspend a
// backgrounded tab/PWA (especially iOS Safari) before it fires. This is the
// best a pure web stack can do: a single absolute-time setTimeout (not a
// repeating interval, which browsers throttle far more aggressively once
// hidden) that calls the already-registered service worker's
// showNotification. Works reliably on Android Chrome with the PWA merely
// backgrounded (not force-closed); not guaranteed on iOS or once the OS
// has fully suspended the page.
export interface ScheduledRestNotification {
  cancel: () => void
}

// No-op cancel object so callers don't need an extra null check when
// scheduling was skipped (permission not granted, or API unsupported).
const NOOP: ScheduledRestNotification = { cancel: () => {} }

export function scheduleRestDoneNotification(
  totalSeconds: number,
  text: string,
): ScheduledRestNotification {
  if (
    !('serviceWorker' in navigator) ||
    !('Notification' in window) ||
    Notification.permission !== 'granted'
  ) {
    return NOOP
  }

  let cancelled = false
  const timeoutId = window.setTimeout(() => {
    if (cancelled) {
      return
    }
    // Only as a system notification when the page isn't the one on screen
    // -- RestTimer's own alertRestDone() (vibration + beep) already covers
    // the athlete looking at the countdown; a second OS banner on top of
    // that would just be noise.
    if (!document.hidden) {
      return
    }
    navigator.serviceWorker.ready
      .then((registration) =>
        registration.showNotification(text, {
          icon: '/favicon.png',
          tag: 'icelevel-rest-done',
          // Not in this project's TS lib.dom version's NotificationOptions
          // type, but a real, widely-supported option (used the same way
          // in public/sw.js's push handler, which is plain JS and doesn't
          // hit this).
          ...({ vibrate: [200, 100, 200] } as NotificationOptions),
        }),
      )
      .catch(() => {
        // Best-effort -- same convention as the rest of push.ts.
      })
  }, totalSeconds * 1000)

  return {
    cancel: () => {
      cancelled = true
      window.clearTimeout(timeoutId)
    },
  }
}

// Rest timers start as a side effect of confirming a set (a real tap), so
// this stays inside that call stack rather than needing its own dedicated
// settings-page toggle -- if permission is already 'granted' or 'denied'
// this resolves immediately without prompting again.
export async function ensureNotificationPermission(): Promise<void> {
  if (!('Notification' in window) || Notification.permission !== 'default') {
    return
  }
  try {
    await Notification.requestPermission()
  } catch {
    // Best-effort -- scheduleRestDoneNotification above re-checks
    // Notification.permission itself and simply no-ops if this didn't end
    // up granted.
  }
}
