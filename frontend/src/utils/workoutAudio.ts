// Lock-screen player for the workout timer -- EXPERIMENT (2026-10-03), off
// unless the athlete turns it on in Settings → Уведомления.
//
// A web page can't draw on the lock screen, but every mobile browser shows
// its own media widget (title, artwork, progress bar, play/pause/next) for a
// page that is playing audio, filled from the Media Session API. Three
// tricks borrowed from small open-source workout/interval PWAs:
//  1. A silent looping <audio> element is what makes the page "media" in
//     the first place -- Chrome on Android then shows the widget and stops
//     suspending the page; iOS shows the widget too. An <audio>, never a
//     <video>: iOS cuts a video's sound the moment the screen locks.
//  2. navigator.audioSession.type = 'playback' (iOS 16.4+) asks iOS to keep
//     the page's audio running with the screen locked (and through the
//     silent switch). Reported reliable from iOS 17.5 on.
//  3. Beeps are scheduled ahead of time on the AudioContext clock rather
//     than fired from JS timers -- the audio thread keeps playing them on
//     time even while iOS has frozen the page's JavaScript. The timer's own
//     state catches up the moment the page wakes (see TimerPlayer).

import { getSharedAudioContext } from './restNotification'

const ENABLED_KEY = 'icelevel.lockScreenPlayer'

export function isLockScreenPlayerEnabled(): boolean {
  try {
    return localStorage.getItem(ENABLED_KEY) === '1'
  } catch {
    return false
  }
}

export function setLockScreenPlayerEnabled(enabled: boolean): void {
  try {
    if (enabled) {
      localStorage.setItem(ENABLED_KEY, '1')
    } else {
      localStorage.removeItem(ENABLED_KEY)
    }
  } catch {
    // Private mode / blocked storage -- the experiment just stays off.
  }
}

export function isLockScreenPlayerSupported(): boolean {
  return 'mediaSession' in navigator
}

// Silence as an in-memory 8 kHz 8-bit mono WAV (8 KB per second), exactly
// as long as the whole exercise. iOS draws the lock-screen progress bar
// from this element's own timeline and ignores setPositionState in a
// home-screen app -- with a short looping clip the bar kept restarting.
// A track as long as the exercise, seeked to the elapsed second, makes the
// bar right even while the page itself is frozen: the track plays on.
const SILENCE_RATE = 8000
const MAX_SILENCE_SECONDS = 20 * 60
let silenceCache: { seconds: number; url: string } | null = null

function silentWavUrl(seconds: number): string {
  const length = Math.max(1, Math.min(MAX_SILENCE_SECONDS, Math.ceil(seconds)))
  if (silenceCache !== null && silenceCache.seconds === length) {
    return silenceCache.url
  }
  const samples = SILENCE_RATE * length
  const buffer = new ArrayBuffer(44 + samples)
  const view = new DataView(buffer)
  const writeText = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) {
      view.setUint8(offset + i, text.charCodeAt(i))
    }
  }
  writeText(0, 'RIFF')
  view.setUint32(4, 36 + samples, true)
  writeText(8, 'WAVE')
  writeText(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, SILENCE_RATE, true)
  view.setUint32(28, SILENCE_RATE, true) // byte rate
  view.setUint16(32, 1, true) // block align
  view.setUint16(34, 8, true) // bits per sample
  writeText(36, 'data')
  view.setUint32(40, samples, true)
  new Uint8Array(buffer, 44).fill(128) // 8-bit PCM silence is the midpoint
  if (silenceCache !== null) {
    URL.revokeObjectURL(silenceCache.url)
  }
  const url = URL.createObjectURL(new Blob([buffer], { type: 'audio/wav' }))
  silenceCache = { seconds: length, url }
  return url
}

let keepAliveAudio: HTMLAudioElement | null = null

export interface LockScreenHandlers {
  onPlay: () => void
  onPause: () => void
  onNext?: () => void
}

export interface LockScreenInfo {
  title: string
  subtitle: string
  artworkUrl?: string
}

// Must be called from inside a real tap (audio.play() needs a gesture).
export function startLockScreenSession(info: LockScreenInfo, handlers: LockScreenHandlers): void {
  if (!isLockScreenPlayerSupported()) {
    return
  }
  const audioSession = (navigator as Navigator & { audioSession?: { type: string } }).audioSession
  if (audioSession !== undefined) {
    try {
      audioSession.type = 'playback'
    } catch {
      // Older iOS -- the widget still works, background audio may not.
    }
  }
  if (keepAliveAudio === null) {
    keepAliveAudio = new Audio()
    keepAliveAudio.loop = true
  }
  // Started here, inside the tap -- later play() calls on the same element
  // (resume from the lock screen, a new track length) are then allowed.
  if (!keepAliveAudio.src) {
    keepAliveAudio.src = silentWavUrl(60)
  }
  void keepAliveAudio.play().catch(() => {})
  updateLockScreenInfo(info)
  const session = navigator.mediaSession
  session.setActionHandler('play', handlers.onPlay)
  session.setActionHandler('pause', handlers.onPause)
  session.setActionHandler('nexttrack', handlers.onNext ?? null)
}

export function updateLockScreenInfo(info: LockScreenInfo): void {
  if (!isLockScreenPlayerSupported()) {
    return
  }
  navigator.mediaSession.metadata = new MediaMetadata({
    title: info.title,
    artist: info.subtitle,
    album: 'IceLevel',
    artwork: info.artworkUrl
      ? [{ src: info.artworkUrl, sizes: '512x512', type: info.artworkUrl.startsWith('data:image/png') ? 'image/png' : 'image/jpeg' }]
      : [],
  })
}

// The lock-screen progress bar: whole exercise (`totalSeconds`), currently
// at `totalSeconds - remainingSeconds`. Set both ways -- setPositionState
// for Chrome, and the silent track's own length and position for iOS.
export function updateLockScreenProgress(totalSeconds: number, remainingSeconds: number, playing: boolean): void {
  if (!isLockScreenPlayerSupported()) {
    return
  }
  navigator.mediaSession.playbackState = playing ? 'playing' : 'paused'
  if (totalSeconds <= 0) {
    return
  }
  const elapsed = Math.min(totalSeconds, Math.max(0, totalSeconds - remainingSeconds))
  if (keepAliveAudio !== null) {
    const url = silentWavUrl(totalSeconds)
    if (keepAliveAudio.src !== url) {
      keepAliveAudio.src = url
    }
    const seekTo = () => {
      if (keepAliveAudio !== null && Math.abs(keepAliveAudio.currentTime - elapsed) > 0.5) {
        keepAliveAudio.currentTime = elapsed
      }
    }
    if (keepAliveAudio.readyState >= 1) {
      seekTo()
    } else {
      keepAliveAudio.addEventListener('loadedmetadata', seekTo, { once: true })
    }
    if (playing) {
      void keepAliveAudio.play().catch(() => {})
    } else {
      keepAliveAudio.pause()
    }
  }
  try {
    navigator.mediaSession.setPositionState({
      duration: totalSeconds,
      position: elapsed,
      playbackRate: playing ? 1 : 1e-6,
    })
  } catch {
    // Some browsers reject an edge value mid-transition -- the next update fixes it.
  }
}

// Exercise over or left: iOS keeps the last "now playing" card on the lock
// screen -- with no metadata it falls back to the bare app icon, so leave a
// branded idle card there instead (`idle`, see lockScreenArtwork.ts).
export function stopLockScreenSession(idle?: LockScreenInfo): void {
  cancelScheduledBeeps()
  if (keepAliveAudio !== null) {
    keepAliveAudio.pause()
  }
  if (!isLockScreenPlayerSupported()) {
    return
  }
  for (const action of ['play', 'pause', 'nexttrack'] as const) {
    navigator.mediaSession.setActionHandler(action, null)
  }
  if (idle !== undefined) {
    updateLockScreenInfo(idle)
    navigator.mediaSession.playbackState = 'paused'
  } else {
    navigator.mediaSession.metadata = null
    navigator.mediaSession.playbackState = 'none'
  }
}

// One timer segment ahead of us: `endsIn` seconds from now, and which tone
// marks its end ('work' ends -> rest starts, 'rest' ends -> work starts,
// 'done' = last round over).
export interface SegmentEnd {
  endsIn: number
  kind: 'work' | 'rest' | 'done'
}

let scheduledNodes: OscillatorNode[] = []

export function cancelScheduledBeeps(): void {
  for (const node of scheduledNodes) {
    try {
      node.stop()
    } catch {
      // Already played.
    }
  }
  scheduledNodes = []
}

function tone(ctx: AudioContext, at: number, frequency: number, length: number): void {
  const oscillator = ctx.createOscillator()
  const gain = ctx.createGain()
  oscillator.frequency.value = frequency
  gain.gain.setValueAtTime(0.25, at)
  gain.gain.exponentialRampToValueAtTime(0.001, at + length)
  oscillator.connect(gain)
  gain.connect(ctx.destination)
  oscillator.start(at)
  oscillator.stop(at + length)
  scheduledNodes.push(oscillator)
}

// Replaces whatever was scheduled before: three short ticks counting down
// the last 3 s of each segment, then its end tone -- high for "go"
// (rest over), lower for "rest" (work over), a double tone when done.
export function scheduleSegmentBeeps(segments: SegmentEnd[]): void {
  cancelScheduledBeeps()
  const ctx = getSharedAudioContext()
  if (ctx === null) {
    return
  }
  if (ctx.state === 'suspended') {
    void ctx.resume()
  }
  const now = ctx.currentTime
  for (const segment of segments) {
    const end = now + segment.endsIn
    for (const before of [3, 2, 1]) {
      if (segment.endsIn - before > 0.05) {
        tone(ctx, end - before, 660, 0.12)
      }
    }
    if (segment.kind === 'rest') {
      tone(ctx, end, 1046, 0.5)
    } else if (segment.kind === 'work') {
      tone(ctx, end, 523, 0.5)
    } else {
      tone(ctx, end, 784, 0.25)
      tone(ctx, end + 0.3, 1046, 0.5)
    }
  }
}
