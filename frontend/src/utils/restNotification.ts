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

function resolveAudioContextClass(): typeof AudioContext | undefined {
  return (
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  )
}

// 2026-09-17 fix (audit item #9): alertTimerDone used to call
// `new AudioContext()` fresh every time it fired -- but it's invoked from
// a setTimeout/interval callback (the countdown reaching 0:00), never
// directly inside a user tap's own event handler. Browsers (iOS Safari in
// particular) only let an AudioContext actually produce sound if it was
// created or resumed synchronously inside a real user gesture; a context
// built inside a timer callback starts (and stays) 'suspended', so
// oscillator.start() ran with no audible output and no error either --
// looked like a bug in the beep itself, but the beep code was always
// correct.
//
// Fix: one shared AudioContext, created/unlocked once from inside the
// very first real tap/click/keydown this session (installAudioUnlock
// below, wired up app-wide in main.tsx) -- alertTimerDone only ever calls
// ctx.resume() on that already-unlocked context afterward, never
// `new AudioContext()` again.
let sharedAudioContext: AudioContext | null = null

// iOS Safari specifically: resume() on an already-unlocked context isn't
// always enough on its own to guarantee future *programmatic* (non-gesture)
// playback stays unlocked -- playing one real (if silent) buffer directly
// inside the unlocking gesture is the documented workaround that reliably
// keeps the context usable for every later timer-fired beep on that page
// load.
function playSilentUnlockBuffer(ctx: AudioContext) {
  const buffer = ctx.createBuffer(1, 1, 22050)
  const source = ctx.createBufferSource()
  source.buffer = buffer
  source.connect(ctx.destination)
  source.start(0)
}

// Call synchronously from inside a real user gesture handler (never from a
// timer callback) -- see the module doc above for why that distinction
// matters. Safe to call more than once; only does real work the first time.
function unlockSharedAudioContext() {
  const AudioContextClass = resolveAudioContextClass()
  if (AudioContextClass === undefined) {
    return
  }
  if (sharedAudioContext === null) {
    try {
      sharedAudioContext = new AudioContextClass()
      playSilentUnlockBuffer(sharedAudioContext)
    } catch {
      // Best-effort -- alertTimerDone below falls back to a fresh (likely
      // still-locked) context if this never succeeded.
      return
    }
  }
  if (sharedAudioContext.state === 'suspended') {
    void sharedAudioContext.resume()
  }
}

// Installs a one-time listener for the session's first real tap/click/
// keydown and unlocks the shared AudioContext from directly inside it --
// call once, app-wide, from main.tsx. Each event type removes itself after
// firing once; 'once: true' handles that without extra bookkeeping.
export function installAudioUnlockOnFirstGesture(): void {
  const options: AddEventListenerOptions = { once: true, capture: true }
  for (const type of ['pointerdown', 'touchstart', 'keydown'] as const) {
    window.addEventListener(type, unlockSharedAudioContext, options)
  }
}

// Vibration + a short synthesized beep (Web Audio oscillator, no external
// audio asset needed) -- the immediate, always-on-screen alert for "a
// countdown just reached zero". Shared by both timer surfaces: RestTimer
// (sets/reps flow, between-set rest) and TimerPlayer (duration-mode media
// player, both the work ring and its own rest ring). Both effects are
// best-effort -- navigator.vibrate isn't available on desktop browsers
// (and never on iOS Safari at all -- Apple hasn't implemented the
// Vibration API in WebKit, not a bug here), and sound can still be
// unavailable if this fires before the user has interacted with the page
// at all this session -- the visual countdown hitting 0:00 is the signal
// that always works regardless of whether either of these actually fires.
export function alertTimerDone() {
  if (typeof navigator.vibrate === 'function') {
    navigator.vibrate(200)
  }
  try {
    const AudioContextClass = resolveAudioContextClass()
    if (AudioContextClass === undefined) {
      return
    }
    // Reuse + resume the already-unlocked shared context (see above)
    // instead of constructing a new one here -- a context built for the
    // first time inside this timer-fired callback would start suspended
    // and never actually produce sound on iOS Safari.
    if (sharedAudioContext === null) {
      sharedAudioContext = new AudioContextClass()
    }
    const ctx = sharedAudioContext
    if (ctx.state === 'suspended') {
      void ctx.resume()
    }
    const oscillator = ctx.createOscillator()
    const gain = ctx.createGain()
    oscillator.frequency.value = 880
    gain.gain.setValueAtTime(0.2, ctx.currentTime)
    oscillator.connect(gain)
    gain.connect(ctx.destination)
    oscillator.start()
    oscillator.stop(ctx.currentTime + 0.3)
    // Not ctx.close() -- this is the shared, reused context now, not a
    // one-shot one; closing it here would break every later beep this
    // session.
  } catch {
    // Best-effort -- see comment above, the visual countdown already
    // reached zero regardless of whether this succeeds.
  }
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
    // -- alertTimerDone() (vibration + beep) already covers the athlete
    // looking at the countdown; a second OS banner on top of that would
    // just be noise.
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
